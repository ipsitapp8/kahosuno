"""IndicTrans2 translation provider: a stub for later.

IndicTrans2 (AI4Bharat) would run self-hosted, which removes the per-call translate cost and
latency of an external API. Not implemented yet: selecting it fails loudly at startup use.
"""

# FLORES-style codes IndicTrans2 expects, for the languages this app supports.
LANG_CODES = {
    "hi-IN": "hin_Deva",
    "kn-IN": "kan_Knda",
    "en-IN": "eng_Latn",
    "bn-IN": "ben_Beng",
    "pa-IN": "pan_Guru",
    "ta-IN": "tam_Taml",
    "te-IN": "tel_Telu",
    "ml-IN": "mal_Mlym",
    "mr-IN": "mar_Deva",
    "gu-IN": "guj_Gujr",
    "od-IN": "ory_Orya",
}


class IndicTrans2Translate:
    async def translate(self, text: str, src: str, tgt: str) -> str:
        if src == tgt or not text.strip():
            return text
        raise NotImplementedError(
            "IndicTrans2 provider is a stub. Set TRANSLATE_PROVIDER=sarvam until it is built."
        )

    async def aclose(self) -> None:
        return None
