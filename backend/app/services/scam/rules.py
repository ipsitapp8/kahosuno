# ruff: noqa: E501  (user-facing Hinglish strings and regex tables read better on one line)
"""Layer 1 of the scam shield: fast weighted regex rules.

Covers English, Hindi (Devanagari), Kannada (script), and romanised Hindi/Kannada
("Hinglish" / "Kanglish"), since STT output and code-mixed speech arrive in all of them.

Scoring: each *category* contributes its strongest matching rule (so repeating a word does
not inflate the score), and categories combine as a noisy-OR:
    risk = 100 * (1 - prod(1 - weight/100))
so one weak signal stays low, but several independent signals escalate quickly.
"""

import re
from dataclasses import dataclass

# Characters that count as "inside a word": Latin word chars plus Devanagari and Kannada blocks.
# Python's \b does not treat Indic combining marks (matras) as word chars, so we build our own.
_W = r"\wऀ-ॿಀ-೿"
ZWNJ = "‌"


def _latin(p: str) -> str:
    return rf"(?<![{_W}])(?:{p})(?![{_W}])"


def _indic(p: str) -> str:
    # Leading boundary only: Hindi and (especially) Kannada attach suffixes to the stem.
    return rf"(?<![{_W}])(?:{p})"


def _rx(latin: str = "", indic: str = "") -> re.Pattern[str]:
    parts = []
    if latin:
        parts.append(_latin(latin))
    if indic:
        parts.append(_indic(indic))
    return re.compile("|".join(parts), re.IGNORECASE)


# Negation near a sharing request ("never share your OTP") turns it into a warning, not a scam.
_NEGATION = re.compile(
    r"\b(?:don'?t|do not|dont|never|not|no one|nobody|mat|nahi|nahin|kabhi nahi|beda|bedi|"
    r"yaarigu|yarigu)\b|मत|नहीं|कभी नहीं|बिल्कुल नहीं|ಬೇಡ|ಯಾರಿಗೂ|ಹೇಳಬೇಡಿ|ಕೊಡಬೇಡಿ",
    re.IGNORECASE,
)

SECRET = r"otp|pin|cvv|password|card number|upi pin"
SECRET_HI = "ओटीपी|ओ\\.?टी\\.?पी|पिन|सीवीवी|पासवर्ड|कार्ड नंबर"
SECRET_KN = f"ಓಟಿಪಿ|ಒಟಿಪಿ|ಪಿನ್|ಸಿವಿವಿ|ಪಾಸ್{ZWNJ}?ವರ್ಡ್|ಕಾರ್ಡ್ ನಂಬರ್"
GIVE_EN = (
    r"tell|share|give|send|read(?: out)?|provide|batao|bata do|bata de|bata dena|bataiye|bolo|boliye|dijiye|dena|"
    r"de do|heli|helu|kodi|kodu|kalisi"
)
GIVE_HI = "बताइए|बताओ|बताएं|बता दो|बोलिए|बोलो|दीजिए|दीजिये|दो(?![ऀ-ॿ])|भेजिए|भेजो|शेयर"
GIVE_KN = "ಹೇಳಿ|ಹೇಳು|ಕೊಡಿ|ಕೊಡು|ಕಳುಹಿಸಿ|ಶೇರ್"
GAP = r"[^.?!।]{0,40}"


@dataclass(frozen=True)
class Rule:
    category: str
    weight: int
    pattern: re.Pattern[str]
    negatable: bool = False


RULES: tuple[Rule, ...] = (
    # --- being asked for a secret (the strongest single signal) ---
    Rule(
        "credential_request",
        70,
        re.compile(
            "|".join(
                [
                    _latin(rf"(?:{GIVE_EN}){GAP}\b(?:{SECRET})"),
                    _latin(rf"(?:{SECRET}){GAP}\b(?:{GIVE_EN})"),
                    _indic(rf"(?:{SECRET_HI}){GAP}(?:{GIVE_HI})"),
                    _indic(rf"(?:{GIVE_HI}){GAP}(?:{SECRET_HI})"),
                    _indic(rf"(?:{SECRET_KN}){GAP}(?:{GIVE_KN})"),
                    _indic(rf"(?:{GIVE_KN}){GAP}(?:{SECRET_KN})"),
                    # romanised words next to a Hindi/Kannada-script request verb and vice versa
                    _latin(rf"(?:{SECRET}){GAP}") + rf"(?:{GIVE_HI}|{GIVE_KN})",
                ]
            ),
            re.IGNORECASE,
        ),
        negatable=True,
    ),
    # --- the secret merely being mentioned ---
    Rule("sensitive_info", 30, _rx(r"otp|one[- ]time password", "ओटीपी|ओ\\.?टी\\.?पी|ಓಟಿಪಿ|ಒಟಿಪಿ")),
    Rule(
        "sensitive_info",
        40,
        _rx(
            r"cvv|atm pin|upi pin|card number|pin(?! ?code)|password",
            f"सीवीवी|पिन(?! ?कोड)|पासवर्ड|कार्ड नंबर|ಸಿವಿವಿ|ಪಿನ್|ಪಾಸ್{ZWNJ}?ವರ್ಡ್|ಕಾರ್ಡ್ ನಂಬರ್",
        ),
    ),
    # --- KYC / identity documents ---
    Rule("kyc", 30, _rx(r"kyc", "केवाईसी|ಕೆವೈಸಿ")),
    Rule("kyc", 15, _rx(r"aadhaar|aadhar|pan card|pan number", "आधार|पैन कार्ड|ಆಧಾರ್|ಪ್ಯಾನ್ ಕಾರ್ಡ್")),
    # --- account / card / SIM about to be blocked ---
    Rule(
        "account_block",
        35,
        _rx(
            r"(?:account|card|sim|khata|khate)\s+(?:will be\s+|is\s+|has been\s+|ho jayega\s+)?"
            r"(?:block(?:ed)?|band|bandh|suspend(?:ed)?|freeze|frozen|clos(?:e|ed)|deactivat\w*)"
            r"|(?:block|freeze|suspend)\w*\s+(?:your|aapka|aapke)\s+(?:account|card|sim)",
            "(?:खाता|खाते|अकाउंट|कार्ड|सिम)\\s*(?:बंद|ब्लॉक|फ्रीज़|फ्रीज|सस्पेंड)"
            "|(?:ಖಾತೆ|ಅಕೌಂಟ್|ಕಾರ್ಡ್|ಸಿಮ್)\\s*(?:ಬ್ಲಾಕ್|ಬಂದ್|ಸ್ಥಗಿತ|ಫ್ರೀಜ್)",
        ),
    ),
    # --- pressure ---
    Rule(
        "urgency",
        12,
        _rx(
            r"immediately|urgent(?:ly)?|right now|last warning|within \d+ (?:minutes?|hours?)|"
            r"turant|jaldi|foran|warna|varna|aaj hi|takshana|takshan|igale|bega|illa andre|"
            r"illandre|illadidre",
            "तुरंत|फौरन|जल्दी|आज ही|वरना|ತಕ್ಷಣ|ಈಗಲೇ|ಬೇಗ|ಇಲ್ಲದಿದ್ದರೆ|ಇಲ್ಲಾಂದ್ರೆ",
        ),
    ),
    # --- police / agencies / "digital arrest" ---
    Rule(
        "authority",
        70,
        _rx(
            r"digital arrest",
            "डिजिटल अरेस्ट|डिजिटल गिरफ्तार|ಡಿಜಿಟಲ್ ಅರೆಸ್ಟ್|ಡಿಜಿಟಲ್ ಬಂಧನ",
        ),
    ),
    Rule(
        "authority",
        45,
        _rx(
            r"arrest warrant|will (?:be )?arrest(?:ed)?(?: you)?|arrest you|money laundering|"
            r"narcotics|cbi|enforcement directorate|giraftar|warrant",
            "गिरफ्तार|वारंट|सीबीआई|नारकोटिक्स|मनी लॉन्ड्रिंग|ವಾರಂಟ್|ಸಿಬಿಐ|ಬಂಧಿಸ|ಬಂಧನ",
        ),
    ),
    Rule("authority", 20, _rx(r"police|customs|cyber ?crime", "पुलिस|ಪೊಲೀಸ್")),
    # --- pretending to be a bank / company officer ---
    Rule(
        "impersonation",
        25,
        _rx(
            r"(?:calling|speaking|call|bol raha(?: hoon| hu)?|bol rahi(?: hoon| hu)?) "
            r"(?:from|se)\s+(?:the\s+)?(?:sbi|hdfc|icici|axis|pnb|rbi|bank|customer care)"
            r"|bank (?:officer|manager|executive)|bank se bol\w*|customer care",
            f"बैंक\\s*(?:से|अधिकारी|मैनेजर)|ಬ್ಯಾಂಕ್{ZWNJ}?\\s*(?:ನಿಂದ|ಅಧಿಕಾರಿ|ಮ್ಯಾನೇಜರ್)",
        ),
    ),
    # --- prizes and advance fees ---
    Rule(
        "lottery",
        45,
        _rx(
            r"lottery|lucky draw|jackpot|kbc|you (?:have )?won|congratulations|inaam|bahumana",
            "लॉटरी|जैकपॉट|केबीसी|इनाम|ಲಾಟರಿ|ಜಾಕ್" + ZWNJ + "?ಪಾಟ್|ಬಹುಮಾನ",
        ),
    ),
    Rule("lottery", 40, _rx(r"prize|cashback", "")),
    Rule(
        "advance_fee",
        40,
        _rx(
            r"processing fee|registration fee|claim (?:your )?(?:prize|reward|refund)",
            "प्रोसेसिंग फीस|रजिस्ट्रेशन फीस|ಪ್ರೊಸೆಸಿಂಗ್ ಫೀ",
        ),
    ),
    # --- courier / parcel / customs-fee trick ---
    Rule(
        "courier_scam",
        45,
        _rx(
            r"(?:parcel|package|courier)\b[^.?!।]{0,40}\b(?:customs|seized|stuck|held|drugs|illegal|fedex)",
            "(?:पार्सल|पैकेज|कूरियर)[^.?!।]{0,40}(?:कस्टम|जब्त|रुका|ड्रग)"
            "|(?:ಪಾರ್ಸೆಲ್|ಪ್ಯಾಕೇಜ್|ಕೊರಿಯರ್)[^.?!।]{0,40}(?:ಕಸ್ಟಮ್ಸ್|ವಶ|ಡ್ರಗ್)",
        ),
    ),
    # --- "electricity will be disconnected tonight" ---
    Rule(
        "utility_scam",
        35,
        _rx(
            r"(?:electricity|bijli|power|light)\b[^.?!]{0,30}\b"
            r"(?:will be (?:disconnected|cut|stopped)|disconnect(?:ed)? (?:tonight|today|in)|"
            r"kat jayegi|kat jaayegi)",
            "बिजली[^.?!।]{0,30}(?:कट|काट|बंद)[^.?!।]{0,15}(?:जाएगी|दी जाएगी)"
            "|ವಿದ್ಯುತ್[^.?!]{0,30}(?:ಕಡಿತ|ಕಟ್)",
        ),
    ),
    # --- remote access apps ---
    Rule(
        "remote_access",
        55,
        _rx(
            r"any ?desk|team ?viewer|quick ?support|rust ?desk|screen ?shar(?:e|ing)|"
            r"remote (?:access|control)",
            "एनीडेस्क|टीमव्यूअर|टीम व्यूअर|स्क्रीन शेयर|ಎನಿಡೆಸ್ಕ್|ಟೀಮ್ ವ್ಯೂವರ್|ಸ್ಕ್ರೀನ್ ಶೇರ್",
        ),
    ),
    # --- UPI / QR tricks ---
    Rule(
        "upi_qr",
        40,
        _rx(
            r"scan\b[^.?!।]{0,25}\bqr|\bqr\b[^.?!।]{0,25}\bscan",
            "क्यूआर[^.?!।]{0,20}स्कैन|स्कैन[^.?!।]{0,20}क्यूआर|ಕ್ಯೂಆರ್[^.?!।]{0,20}ಸ್ಕ್ಯಾನ್",
        ),
    ),
    Rule(
        "upi_qr",
        35,
        _rx(
            r"(?:accept|approve)\b[^.?!।]{0,20}\b(?:request|collect)|"
            r"(?:request|collect)\b[^.?!।]{0,20}\b(?:accept|approve)",
            "",
        ),
    ),
    Rule(
        "upi_qr",
        15,
        _rx(r"upi|qr ?code|google ?pay|gpay|phone ?pe|paytm|bhim", "यूपीआई|ಯುಪಿಐ|फोन ?पे"),
    ),
)

# What to tell the listener, in Hinglish, per category.
REASONS_HINGLISH: dict[str, str] = {
    "credential_request": "Aapse OTP/PIN/password maang rahe hain. Asli bank kabhi ye nahi maangta.",
    "sensitive_info": "OTP, PIN ya card ki jaankari ki baat ho rahi hai. Savdhaan rahein.",
    "kyc": "KYC update ke naam par call. Asli bank phone par KYC nahi karwata.",
    "account_block": "Account/card/SIM band hone ka darr dikha rahe hain.",
    "urgency": "Jaldi karne ka dabaav bana rahe hain. Thehar kar sochiye.",
    "authority": "Police/CBI ya 'digital arrest' ka darr. Digital arrest jaisi koi cheez hoti hi nahi.",
    "impersonation": "Bank ya company ka officer banke baat kar rahe hain. Khud bank ko call karke poochiye.",
    "lottery": "Inaam ya lottery ka lalach. Jo lottery aapne kharidi hi nahi, wo aap jeet nahi sakte.",
    "advance_fee": "Inaam/refund ke liye pehle paisa maang rahe hain. Ye fraud hai.",
    "courier_scam": "Parcel/courier mein drugs ya customs fee ka bahana. Asli courier phone par paisa nahi maangta.",
    "utility_scam": "Bijli kat jaane ki dhamki. Bijli board aise phone par nahi dhamkata, bill khud check karein.",
    "remote_access": "Phone/screen dikhane wali app (AnyDesk, TeamViewer) install karwa rahe hain. Mat karein.",
    "upi_qr": "QR scan ya request approve karne ko keh rahe hain. Paise lene ke liye QR scan nahi karna padta.",
}


@dataclass(frozen=True)
class RuleResult:
    risk: int
    categories: dict[str, int]  # category -> strongest matching weight

    @property
    def top_category(self) -> str:
        return max(self.categories, key=lambda c: self.categories[c]) if self.categories else "none"

    def reasons(self, limit: int = 3) -> list[str]:
        ranked = sorted(self.categories, key=lambda c: -self.categories[c])
        return [REASONS_HINGLISH[c] for c in ranked[:limit]]


def _negated(text: str, start: int, end: int) -> bool:
    return bool(_NEGATION.search(text[max(0, start - 14) : end + 14]))


def score_rules(turns: list[str]) -> RuleResult:
    """Score a window of recent turns (the other person's words)."""
    text = ". ".join(t.strip() for t in turns if t.strip())
    best: dict[str, int] = {}
    for rule in RULES:
        if best.get(rule.category, 0) >= rule.weight:
            continue
        for m in rule.pattern.finditer(text):
            if rule.negatable and _negated(text, m.start(), m.end()):
                continue
            best[rule.category] = rule.weight
            break
    clear = 1.0
    for weight in best.values():
        clear *= 1 - weight / 100
    return RuleResult(risk=round(100 * (1 - clear)), categories=best)
