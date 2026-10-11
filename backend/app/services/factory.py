"""Build the STT / translate / TTS providers chosen in config."""

from dataclasses import dataclass

from app.core.config import Settings
from app.services.gnani import GnaniClient
from app.services.indictrans2 import IndicTrans2Translate
from app.services.pipeline import TranslationPipeline
from app.services.providers import STTProvider, TranslateProvider, TTSProvider
from app.services.sarvam import SarvamClient


@dataclass
class Providers:
    stt: STTProvider
    translate: TranslateProvider
    tts: TTSProvider
    _closers: list[SarvamClient | GnaniClient | IndicTrans2Translate]

    def pipeline(self) -> TranslationPipeline:
        return TranslationPipeline(self.stt, self.translate, self.tts)

    async def aclose(self) -> None:
        for c in self._closers:
            await c.aclose()


def build_providers(settings: Settings) -> Providers:
    sarvam = SarvamClient(settings)
    gnani = GnaniClient(settings)
    closers: list[SarvamClient | GnaniClient | IndicTrans2Translate] = []

    def pick_voice(name: str) -> SarvamClient | GnaniClient:
        if name == "gnani":
            return gnani
        if name == "sarvam":
            return sarvam
        raise ValueError(f"Unknown provider {name!r} (use 'gnani' or 'sarvam')")

    stt = pick_voice(settings.stt_provider)
    tts = pick_voice(settings.tts_provider)
    translate: TranslateProvider
    if settings.translate_provider == "sarvam":
        translate = sarvam
    elif settings.translate_provider == "indictrans2":
        translate = it2 = IndicTrans2Translate()
        closers.append(it2)
    else:
        raise ValueError(
            f"Unknown translate provider {settings.translate_provider!r} "
            "(use 'sarvam' or 'indictrans2')"
        )
    closers += [sarvam, gnani]
    return Providers(stt=stt, translate=translate, tts=tts, _closers=closers)
