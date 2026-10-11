# Bharat Call Assistant: WebSocket protocol v1

## Joining
1. `POST /rooms` with `{"language": "od-IN", "name": "Ramesh", "consent": true}` returns
   `{"room_id": "...", "code": "483920", "token": "<JWT>"}`. The token lasts 10 minutes.
   A second person joins with the room code: `POST /rooms/{code}/join` (same body) returns their token.
2. Connect to `ws(s)://<host>/ws/v1/rooms/{room_id}?token=<JWT>`.
3. The first client message must be `hello`. Rooms hold at most 2 participants.

Supported language codes: `od-IN`, `hi-IN`, `bn-IN`, `en-IN`, `pa-IN` (first pair: `od-IN` <-> `hi-IN`).

## Frames
- **Text frames** carry JSON: `{"v": 1, "type": "<name>", ...}`.
- **Binary frames** carry audio: byte 0 is the frame type, the rest is the payload.
  - Client to server: `0x01` = microphone audio, 16 kHz mono PCM16 little-endian, about 100 ms (3200 bytes) per frame.
  - Server to client: `0x02` = translated speech, 16 kHz mono PCM16, variable length.
- Limits: a binary frame over 16 KB, or more than 25 s of audio in one utterance, is rejected with an `error`.

## Client to server (JSON)
| type | fields | notes |
|---|---|---|
| `hello` | `name`, `language`, `consent` (must be `true`), `mode` (`auto` or `ptt`), `store_transcript` (default `false`) | First message. Without consent the server sends `error` (`consent_required`) and closes. |
| `mode` | `mode` | Switch between `auto` (server-side VAD) and `ptt`. |
| `ptt_start` / `ptt_end` | none | Mark utterance boundaries in `ptt` mode. |
| `ping` | none | Keepalive, answered by `pong`. |
| `bye` | none | Graceful leave. |

## Server to client (JSON)
| type | fields | notes |
|---|---|---|
| `joined` | `participant_id`, `peer` (name and language, or `null`) | Reply to `hello`. |
| `peer_joined` / `peer_left` | `name`, `language` | `peer_left` is sent after the reconnect grace period (10 s). |
| `transcript` | `utterance_id`, `speaker` (`self`/`peer`), `original`, `translated`, `tone` | Sent to both sides when translation is ready. `tone` is `calm` until Phase 5. Silence and noise produce no transcript. |
| `tts_start` / `tts_end` | `utterance_id` | Wrap the binary `0x02` frames of one utterance. |
| `latency` | `utterance_id`, `stt_ms`, `translate_ms`, `tts_ms`, `total_ms` | Sent to both sides after the speech is delivered. `tts_ms` is time to first audio; `total_ms` is end of speech to first audio. |
| `scam_alert` | `level` (`none`/`suspicious`/`high`), `risk` (0-100), `category`, `reasons_hinglish` | Sent only to the person who is listening to the suspicious speaker. |
| `error` | `code`, `message`, `fatal` | Non-fatal errors never close the call. |
| `pong` | none | |

`tone` is one of `calm`, `excited`, `angry`, `sad`.

## Error codes
`consent_required`, `bad_token`, `room_full`, `room_not_found`, `rate_limited`, `frame_too_large`,
`utterance_too_long`, `upstream_failed` (Sarvam call failed, utterance dropped, call continues), `bad_message`.

## Reconnect
Reconnect with the same token within its validity. The server keeps the participant slot for 10 s after a
disconnect and then announces `peer_left`. On reconnect the client sends `hello` again; state is not replayed.

## Versioning
The version is in the URL (`/ws/v1/...`) and in every JSON message (`"v": 1`). Breaking changes bump the
version. Unknown message types are ignored by clients and answered with `bad_message` by the server.
