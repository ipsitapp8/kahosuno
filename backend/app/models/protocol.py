"""Wire protocol v1 messages. See docs/protocol.md."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

PROTOCOL_VERSION = 1
SUPPORTED_LANGUAGES = frozenset({"od-IN", "hi-IN", "bn-IN", "en-IN", "pa-IN"})

AUDIO_IN = 0x01  # client -> server microphone frame
AUDIO_OUT = 0x02  # server -> client translated speech frame

Mode = Literal["auto", "ptt"]
Tone = Literal["calm", "excited", "angry", "sad"]


class _Msg(BaseModel):
    v: int = PROTOCOL_VERSION


# ---- client -> server ----
class Hello(_Msg):
    type: Literal["hello"]
    name: str
    language: str
    consent: bool
    mode: Mode = "auto"
    store_transcript: bool = False


class SetMode(_Msg):
    type: Literal["mode"]
    mode: Mode


class PttStart(_Msg):
    type: Literal["ptt_start"]


class PttEnd(_Msg):
    type: Literal["ptt_end"]


class Ping(_Msg):
    type: Literal["ping"]


class Bye(_Msg):
    type: Literal["bye"]


ClientMessage = Annotated[
    Hello | SetMode | PttStart | PttEnd | Ping | Bye, Field(discriminator="type")
]
_client_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


def parse_client_message(text: str) -> ClientMessage:
    return _client_adapter.validate_json(text)


# ---- server -> client ----
class PeerInfo(BaseModel):
    name: str
    language: str


class Joined(_Msg):
    type: Literal["joined"] = "joined"
    participant_id: str
    peer: PeerInfo | None


class PeerJoined(_Msg):
    type: Literal["peer_joined"] = "peer_joined"
    name: str
    language: str


class PeerLeft(_Msg):
    type: Literal["peer_left"] = "peer_left"
    name: str
    language: str


class Transcript(_Msg):
    type: Literal["transcript"] = "transcript"
    utterance_id: str
    speaker: Literal["self", "peer"]
    original: str
    translated: str
    tone: Tone = "calm"


class TtsStart(_Msg):
    type: Literal["tts_start"] = "tts_start"
    utterance_id: str


class TtsEnd(_Msg):
    type: Literal["tts_end"] = "tts_end"
    utterance_id: str


class LatencyMsg(_Msg):
    type: Literal["latency"] = "latency"
    utterance_id: str
    stt_ms: int
    translate_ms: int
    tts_ms: int
    total_ms: int


class ScamAlert(_Msg):
    type: Literal["scam_alert"] = "scam_alert"
    level: Literal["none", "suspicious", "high"]
    risk: int
    category: str
    reasons_hinglish: list[str]


class ErrorMsg(_Msg):
    type: Literal["error"] = "error"
    code: str
    message: str
    fatal: bool = False


class Pong(_Msg):
    type: Literal["pong"] = "pong"


ServerMessage = (
    Joined | PeerJoined | PeerLeft | Transcript | TtsStart | TtsEnd | LatencyMsg
    | ScamAlert | ErrorMsg | Pong
)
