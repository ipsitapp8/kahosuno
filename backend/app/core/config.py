from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    sarvam_api_key: SecretStr = SecretStr("")
    sarvam_base_url: str = "https://api.sarvam.ai"
    sarvam_timeout_s: float = 30.0
    sarvam_max_retries: int = 2

    stt_model: str = "saaras:v4"
    translate_model: str = "mayura:v1"
    translate_mode: str = "modern-colloquial"
    tts_model: str = "bulbul:v3"
    chat_model: str = "sarvam-105b"

    jwt_secret: SecretStr = SecretStr("change-me")
    jwt_ttl_s: int = 600
    max_frame_bytes: int = 16384
    max_utterance_s: int = 25
    reconnect_grace_s: float = 10.0
    rooms_per_minute: int = 20
    database_url: str = "sqlite+aiosqlite:///./calls.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
