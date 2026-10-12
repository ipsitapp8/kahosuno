from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    sarvam_api_key: SecretStr = SecretStr("")
    sarvam_base_url: str = "https://api.sarvam.ai"
    sarvam_timeout_s: float = 30.0
    sarvam_max_retries: int = 2

    # Vendor per stage. stt/tts: "gnani" | "sarvam". translate: "sarvam" | "indictrans2".
    stt_provider: str = "gnani"
    tts_provider: str = "gnani"
    translate_provider: str = "sarvam"

    gnani_api_key: SecretStr = SecretStr("")
    gnani_base_url: str = "https://api.vachana.ai"
    gnani_timeout_s: float = 30.0
    gnani_max_retries: int = 2
    gnani_tts_model: str = "timbre-v2.5"
    gnani_stt_format: str = "transcribe"  # "verbatim" or "transcribe" (adds ITN)

    stt_model: str = "saaras:v4"
    # Chosen by benchmark (scripts/smoke.py translate-bench): pure target-language output, faster.
    translate_model: str = "sarvam-translate:v1"
    translate_mode: str = "modern-colloquial"  # only used by mayura:v1
    tts_model: str = "bulbul:v3"
    chat_model: str = "sarvam-105b"

    # Scam shield. Rules always run; the LLM layer is optional and falls back to rules on failure.
    scam_enabled: bool = True
    scam_llm_enabled: bool = True
    scam_llm_timeout_s: float = 4.0
    scam_llm_min_interval_s: float = 15.0
    scam_llm_max_calls: int = 20

    # "production" turns on startup safety checks (see check_production).
    app_env: str = "development"
    jwt_secret: SecretStr = SecretStr("change-me")
    jwt_ttl_s: int = 3600  # how long a join token works: also bounds how long a call can reconnect
    join_ttl_s: float = 600  # a token that is never used gives its seat back after this long
    max_frame_bytes: int = 16384
    max_utterance_s: int = 25
    reconnect_grace_s: float = 10.0
    rooms_per_minute: int = 20  # per IP, for creating or joining rooms
    ws_connects_per_minute: int = 120  # per IP, for websocket connections
    max_rooms: int = 200  # open rooms at once: the server keeps them in memory
    database_url: str = "sqlite+aiosqlite:///./calls.db"
    transcript_retention_days: int = 7  # opt-in transcript lines are deleted after this

    def check_production(self) -> None:
        """Refuse to start in production with a guessable signing secret."""
        if self.app_env != "production":
            return
        secret = self.jwt_secret.get_secret_value()
        weak = secret in _WEAK_SECRETS or len(secret) < 32
        if weak:
            raise RuntimeError(
                "APP_ENV=production needs JWT_SECRET to be a random string of at least 32 "
                "characters (anyone could forge join tokens otherwise)."
            )


_WEAK_SECRETS = {"", "change-me", "change-me-to-a-long-random-string"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
