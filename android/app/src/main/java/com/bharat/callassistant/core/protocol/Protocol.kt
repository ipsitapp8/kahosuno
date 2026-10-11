package com.bharat.callassistant.core.protocol

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonObjectBuilder
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put

/** Wire protocol v1. Mirrors docs/protocol.md on the backend. */
const val PROTOCOL_VERSION = 1

/** Audio frames: byte 0 is the type, the rest is 16 kHz mono PCM16 little-endian. */
const val AUDIO_IN: Byte = 0x01 // microphone, client to server
const val AUDIO_OUT: Byte = 0x02 // translated speech, server to client

const val SAMPLE_RATE = 16_000
const val FRAME_BYTES = 3_200 // 100 ms of 16 kHz mono PCM16

enum class TalkMode(val wire: String) {
    Auto("auto"),
    PushToTalk("ptt");

    companion object {
        fun fromWire(value: String?): TalkMode = entries.firstOrNull { it.wire == value } ?: Auto
    }
}

enum class Speaker { Self, Peer }

enum class ScamLevel {
    None, Suspicious, High;

    companion object {
        fun fromWire(value: String?): ScamLevel = when (value) {
            "suspicious" -> Suspicious
            "high" -> High
            else -> None
        }
    }
}

data class PeerInfo(val name: String, val language: String)

sealed interface ServerMessage {
    data class Joined(val participantId: String, val peer: PeerInfo?) : ServerMessage
    data class PeerJoined(val name: String, val language: String) : ServerMessage
    data class PeerLeft(val name: String, val language: String) : ServerMessage
    data class Transcript(
        val utteranceId: String,
        val speaker: Speaker,
        val original: String,
        val translated: String,
        val tone: String,
    ) : ServerMessage

    data class TtsStart(val utteranceId: String) : ServerMessage
    data class TtsEnd(val utteranceId: String) : ServerMessage
    data class Latency(
        val utteranceId: String,
        val sttMs: Int,
        val translateMs: Int,
        val ttsMs: Int,
        val totalMs: Int,
    ) : ServerMessage

    data class ScamAlert(
        val level: ScamLevel,
        val risk: Int,
        val category: String,
        val reasons: List<String>,
    ) : ServerMessage

    data class Error(val code: String, val message: String, val fatal: Boolean) : ServerMessage
    data object Pong : ServerMessage

    /** A message type this client does not know. Ignored, as the protocol requires. */
    data class Unknown(val type: String) : ServerMessage
}

object Protocol {
    val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    /** Parse one server text frame. Never throws: bad input becomes [ServerMessage.Unknown]. */
    fun parse(text: String): ServerMessage {
        val obj: JsonObject = try {
            json.parseToJsonElement(text).jsonObject
        } catch (e: Exception) {
            return ServerMessage.Unknown("invalid_json")
        }
        return try {
            when (val type = obj.str("type")) {
                "joined" -> ServerMessage.Joined(
                    participantId = obj.str("participant_id"),
                    peer = (obj["peer"] as? JsonObject)?.let {
                        PeerInfo(it.str("name"), it.str("language"))
                    },
                )
                "peer_joined" -> ServerMessage.PeerJoined(obj.str("name"), obj.str("language"))
                "peer_left" -> ServerMessage.PeerLeft(obj.str("name"), obj.str("language"))
                "transcript" -> ServerMessage.Transcript(
                    utteranceId = obj.str("utterance_id"),
                    speaker = if (obj.str("speaker") == "self") Speaker.Self else Speaker.Peer,
                    original = obj.str("original"),
                    translated = obj.str("translated"),
                    tone = obj.str("tone", "calm"),
                )
                "tts_start" -> ServerMessage.TtsStart(obj.str("utterance_id"))
                "tts_end" -> ServerMessage.TtsEnd(obj.str("utterance_id"))
                "latency" -> ServerMessage.Latency(
                    utteranceId = obj.str("utterance_id"),
                    sttMs = obj.int("stt_ms"),
                    translateMs = obj.int("translate_ms"),
                    ttsMs = obj.int("tts_ms"),
                    totalMs = obj.int("total_ms"),
                )
                "scam_alert" -> ServerMessage.ScamAlert(
                    level = ScamLevel.fromWire(obj.str("level")),
                    risk = obj.int("risk"),
                    category = obj.str("category"),
                    reasons = (obj["reasons_hinglish"] as? JsonArray)
                        ?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull }
                        ?: emptyList(),
                )
                "error" -> ServerMessage.Error(
                    code = obj.str("code"),
                    message = obj.str("message"),
                    fatal = (obj["fatal"] as? JsonPrimitive)?.booleanOrNull ?: false,
                )
                "pong" -> ServerMessage.Pong
                else -> ServerMessage.Unknown(type)
            }
        } catch (e: Exception) {
            ServerMessage.Unknown("malformed")
        }
    }

    private fun JsonObject.str(key: String, default: String = ""): String =
        (this[key] as? JsonPrimitive)?.contentOrNull ?: default

    private fun JsonObject.int(key: String): Int =
        (this[key] as? JsonPrimitive)?.intOrNull ?: 0

    // ---- client messages ----
    private fun message(type: String, extra: (JsonObjectBuilder.() -> Unit)? = null): String =
        buildJsonObject {
            put("v", PROTOCOL_VERSION)
            put("type", type)
            extra?.invoke(this)
        }.toString()

    fun hello(name: String, language: String, mode: TalkMode): String = message("hello") {
        put("name", name)
        put("language", language)
        put("consent", true)
        put("mode", mode.wire)
        put("store_transcript", false)
    }

    fun mode(mode: TalkMode): String = message("mode") { put("mode", mode.wire) }
    fun pttStart(): String = message("ptt_start")
    fun pttEnd(): String = message("ptt_end")
    fun ping(): String = message("ping")
    fun bye(): String = message("bye")

    // ---- audio frames ----
    /** Wrap one microphone chunk for the server. */
    fun micFrame(pcm: ByteArray): ByteArray {
        val out = ByteArray(pcm.size + 1)
        out[0] = AUDIO_IN
        System.arraycopy(pcm, 0, out, 1, pcm.size)
        return out
    }

    /** Extract speech PCM from a server binary frame, or null if it is not a speech frame. */
    fun speechPcm(frame: ByteArray): ByteArray? =
        if (frame.size > 1 && frame[0] == AUDIO_OUT) frame.copyOfRange(1, frame.size) else null
}
