# ruff: noqa: E501  (sample sentences are data)
"""Layer-1 rules on scam and normal sentences in English, Hindi, Kannada and code-mixed speech."""

import pytest

from app.services.scam.rules import score_rules

YELLOW, RED = 40, 70

# (sentence, minimum risk). RED means a clear, dangerous scam; YELLOW means "be careful".
SCAMS: list[tuple[str, int]] = [
    # English
    ("This is the CBI. A digital arrest warrant has been issued in your name, stay on video.", RED),
    ("Sir, I am calling from SBI bank. Your KYC has expired, share the OTP immediately or your "
     "account will be blocked.", RED),
    ("Congratulations, you have won a lottery of 25 lakh rupees. Pay the processing fee to claim "
     "your prize.", YELLOW),
    ("Please download AnyDesk so I can fix your bank account problem.", YELLOW),
    ("Scan this QR code and approve the collect request to receive your refund.", YELLOW),
    ("Tell me the CVV and PIN on your card.", RED),
    ("There is a parcel in your name with drugs, the narcotics team will arrest you unless you "
     "pay now.", YELLOW),
    ("Sir your electricity will be disconnected tonight, call this number immediately.", YELLOW),
    ("Your courier from FedEx is stuck at customs, pay the fee to release it.", YELLOW),
    # Hindi
    ("आपका पैकेज कस्टम में रुका है, फीस भेजिए, वरना पुलिस आएगी।", YELLOW),
    ("मैं बैंक से बोल रहा हूँ, आपका केवाईसी अपडेट नहीं हुआ, तुरंत अपना ओटीपी बताइए।", RED),
    ("आपके नाम पर डिजिटल अरेस्ट का वारंट जारी हुआ है, सीबीआई अफसर से बात कीजिए।", RED),
    ("आपने लॉटरी जीती है, इनाम पाने के लिए पहले पाँच हज़ार रुपये भेजिए।", YELLOW),
    ("अपना एटीएम पिन बताइए वरना आपका खाता बंद हो जाएगा।", RED),
    # Hinglish
    ("Bhai ATM ka pin bata de, mujhe paisa nikalna hai.", RED),
    ("Aapka account block ho jayega, abhi OTP batao warna sab paisa chala jayega.", RED),
    ("Main police station se bol raha hoon, aapke parcel mein drugs mile hain, digital arrest "
     "ho jayega.", RED),
    ("AnyDesk download karo aur screen share karo, main aapka KYC update kar dunga.", YELLOW),
    ("Bhai ye QR code scan karo, paisa aapke account mein aa jayega.", YELLOW),
    ("Aap apna UPI PIN bataiye, main refund bhej deta hoon.", RED),
    ("Aapka KYC expire ho gaya hai, bank se bol raha hoon, link par click karke update karo.", YELLOW),
    # Kannada script
    ("ನಾನು ಬ್ಯಾಂಕ್‌ನಿಂದ ಮಾತನಾಡುತ್ತಿದ್ದೇನೆ, ನಿಮ್ಮ ಕೆವೈಸಿ ಅಪ್‌ಡೇಟ್ ಆಗಿಲ್ಲ, ತಕ್ಷಣ ನಿಮ್ಮ ಓಟಿಪಿ ಹೇಳಿ.", RED),
    ("ನಿಮ್ಮ ಖಾತೆ ಬ್ಲಾಕ್ ಆಗುತ್ತದೆ, ಈಗಲೇ ಪಿನ್ ಕೊಡಿ.", RED),
    ("ನೀವು ಲಾಟರಿ ಗೆದ್ದಿದ್ದೀರಿ, ಬಹುಮಾನ ಪಡೆಯಲು ಮೊದಲು ಹಣ ಕಳುಹಿಸಿ.", YELLOW),
    ("ಡಿಜಿಟಲ್ ಅರೆಸ್ಟ್ ವಾರಂಟ್ ಬಂದಿದೆ, ಸಿಬಿಐ ಅಧಿಕಾರಿ ಜೊತೆ ಮಾತನಾಡಿ.", RED),
    ("ಎನಿಡೆಸ್ಕ್ ಡೌನ್‌ಲೋಡ್ ಮಾಡಿ, ಸ್ಕ್ರೀನ್ ಶೇರ್ ಮಾಡಿ.", YELLOW),
    # Kanglish (Kannada in Roman letters)
    ("Sir nimma KYC update aagilla, nimma account block aagutte, OTP heli.", RED),
    ("Nimma pin number kodi, illa andre card block aagutte.", RED),
    ("Neevu lottery gedde iddira, prize togollalu modalu hana kalisi.", YELLOW),
    ("Digital arrest aagide, CBI officer jothe matadi.", RED),
    ("AnyDesk download maadi, nanna jothe screen share maadi.", YELLOW),
]

NORMALS: list[str] = [
    # English
    "Hello, how are you? I will call you back after dinner.",
    "Mom, I reached Bangalore safely, the work starts tomorrow.",
    "Please never share your OTP with anyone, the bank said it is not safe.",
    "I paid the rent through PhonePe yesterday.",
    "The police came to our village to check the road work.",
    "I updated my KYC at the bank branch yesterday.",
    "Send me the photos of the new house when you can.",
    "Come home immediately, grandma is not well.",
    # Hindi
    "माँ, मैं ठीक हूँ, इस महीने की तनख्वाह कल मिलेगी।",
    "बैंक वाले ने कहा कि अपना ओटीपी किसी को मत बताइए।",
    "आज बारिश बहुत हो रही है, खेत में पानी भर गया।",
    "मैंने कल बैंक जाकर अपना केवाईसी करवा लिया।",
    "पुलिस ने रास्ते की जाँच की, सब ठीक है।",
    "तुरंत घर आ जाओ, दादी की तबीयत ठीक नहीं है।",
    "मेरे दोस्त ने कहा कि वो कल गाँव आएगा।",
    "The electricity was cut for two hours yesterday because of the storm.",
    "My courier arrived yesterday, the parcel had clothes for the kids.",
    # Hinglish
    "Abhi khana kha raha hoon, thodi der mein call karta hoon.",
    "Bhai, PhonePe se paisa bhej diya, check kar lena.",
    "Mera OTP aa gaya, ab login ho gaya.",
    "Pin code 560001 hai, ghar ka address likh lo.",
    # Kannada script
    "ಅಮ್ಮ, ನಾನು ಸುರಕ್ಷಿತವಾಗಿ ತಲುಪಿದ್ದೇನೆ, ನಾಳೆ ಕೆಲಸ ಶುರು.",
    "ದಯವಿಟ್ಟು ನಿಮ್ಮ ಓಟಿಪಿ ಯಾರಿಗೂ ಹೇಳಬೇಡಿ.",
    "ಬೇಗ ಮನೆಗೆ ಬನ್ನಿ, ಅಪ್ಪನ ಆರೋಗ್ಯ ಸರಿಯಿಲ್ಲ.",
    "ನಾನು ನಿನ್ನೆ ಬ್ಯಾಂಕ್‌ಗೆ ಹೋಗಿ ಕೆವೈಸಿ ಮಾಡಿಸಿದೆ.",
    "ಪೊಲೀಸ್ ಠಾಣೆ ಹತ್ತಿರ ಬಸ್ ನಿಲ್ದಾಣ ಇದೆ.",
    # Kanglish
    "Amma, naanu chennagiddini, ivattu sambala bandide.",
    "Bega mane ge bari, appa ge health sari illa.",
    "Nanna OTP bandide, login aaytu.",
    "Ivattu PhonePe nalli hana kalisidde.",
]


def test_enough_samples() -> None:
    assert len(SCAMS) >= 15 and len(NORMALS) >= 15


@pytest.mark.parametrize(("text", "minimum"), SCAMS)
def test_scam_sentences_are_flagged(text: str, minimum: int) -> None:
    res = score_rules([text])
    assert res.risk >= minimum, f"risk {res.risk} {res.categories} for: {text}"


@pytest.mark.parametrize("text", NORMALS)
def test_normal_sentences_stay_below_warning(text: str) -> None:
    res = score_rules([text])
    assert res.risk < YELLOW, f"risk {res.risk} {res.categories} for: {text}"


def test_warning_not_to_share_otp_is_not_a_request() -> None:
    """The negation guard: 'never share OTP' must not read as 'share OTP'."""
    for text in (
        "Never share your OTP with anyone.",
        "Don't tell your PIN to the caller.",
        "ओटीपी किसी को मत बताइए।",
        "ನಿಮ್ಮ ಓಟಿಪಿ ಯಾರಿಗೂ ಹೇಳಬೇಡಿ.",
    ):
        assert "credential_request" not in score_rules([text]).categories, text


def test_request_in_same_sentence_as_earlier_negation_still_counts() -> None:
    res = score_rules(["अपडेट नहीं हुआ, तुरंत अपना ओटीपी बताइए।"])
    assert "credential_request" in res.categories


def test_repeating_a_word_does_not_inflate_risk() -> None:
    once = score_rules(["OTP"]).risk
    many = score_rules(["OTP OTP OTP OTP OTP"]).risk
    assert once == many


def test_independent_signals_add_up() -> None:
    one = score_rules(["Your KYC is pending."]).risk
    two = score_rules(["Your KYC is pending. Your account will be blocked."]).risk
    three = score_rules(["Your KYC is pending. Your account will be blocked. Do it immediately."]).risk
    assert one < two < three


def test_signals_across_turns_are_combined() -> None:
    risk = score_rules(["I am calling from SBI bank.", "Your KYC has expired."]).risk
    assert risk >= YELLOW > score_rules(["I am calling from SBI bank."]).risk


def test_word_boundaries_avoid_substring_hits() -> None:
    for text in ("The spinning wheel", "Shopping is fun", "He is a cbiology student", "Pinterest"):
        assert score_rules([text]).risk == 0, text


def test_reasons_are_hinglish_and_ranked() -> None:
    res = score_rules(["share the OTP now, your account will be blocked"])
    assert res.top_category == "credential_request"
    assert res.reasons()[0].startswith("Aapse OTP")
    assert len(res.reasons()) <= 3


# Real speech-to-text output spells acronyms out letter by letter. Found on the emulator:
# Gnani returned "के वाई सी" and "ओ टी पी", which the first version of the rules missed.
SPELLED_OUT_SCAMS: list[tuple[str, int]] = [
    ("मैं बैंक से बोल रहा हूँ, आपका के वाई सी अपडेट नहीं हुआ, तुरंत अपना ओ टी पी बताइये।", RED),
    ("आपका के वाई सी पूरा नहीं है, ओ.टी.पी. बताइए।", RED),
    ("अपना सी वी वी और पिन बताइए।", RED),
    ("Sir your K Y C has expired, please tell me the O T P now.", RED),
    ("Share the c v v and pin of your card.", RED),
    ("ನಿಮ್ಮ ಕೆ ವೈ ಸಿ ಅಪ್‌ಡೇಟ್ ಆಗಿಲ್ಲ, ಓ ಟಿ ಪಿ ಹೇಳಿ.", RED),
]


@pytest.mark.parametrize(("text", "minimum"), SPELLED_OUT_SCAMS)
def test_spelled_out_acronyms_are_still_caught(text: str, minimum: int) -> None:
    res = score_rules([text])
    assert res.risk >= minimum, f"risk {res.risk} {res.categories} for: {text}"


def test_spelled_out_warning_is_still_a_warning() -> None:
    for text in ("ओ टी पी किसी को मत बताइए।", "Never tell anyone your O T P."):
        assert "credential_request" not in score_rules([text]).categories, text
