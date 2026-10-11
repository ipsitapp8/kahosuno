package com.bharat.callassistant.call

import com.bharat.callassistant.core.protocol.PeerInfo
import com.bharat.callassistant.core.protocol.ScamLevel
import com.bharat.callassistant.core.protocol.ServerMessage
import com.bharat.callassistant.core.protocol.Speaker
import com.bharat.callassistant.core.protocol.TalkMode
import kotlinx.coroutines.flow.StateFlow

enum class Phase { Idle, Connecting, Waiting, InCall, Reconnecting, Ended }

enum class EndReason { HangUp, ConnectionLost, ServerError, AudioError }

/** Everything a call needs to connect. Built by the join screen. */
data class CallParams(
    val serverUrl: String,
    val roomId: String,
    val code: String,
    val token: String,
    val name: String,
    val language: String,
    val mode: TalkMode,
)

data class TranscriptItem(
    val utteranceId: String,
    val speaker: Speaker,
    val original: String,
    val translated: String,
    val tone: String,
    val latencyMs: Int? = null,
) {
    val key: String get() = "$utteranceId-${speaker.name}"
}

data class ScamState(
    val level: ScamLevel,
    val risk: Int,
    val category: String,
    val reasons: List<String>,
    val dismissed: Boolean = false,
)

data class CallUiState(
    val phase: Phase = Phase.Idle,
    val roomCode: String = "",
    val myName: String = "",
    val myLanguage: String = "",
    val peer: PeerInfo? = null,
    val transcript: List<TranscriptItem> = emptyList(),
    /** Tone of the other person's last utterance. */
    val tone: String? = null,
    val lastLatencyMs: Int? = null,
    val peerSpeaking: Boolean = false,
    val muted: Boolean = false,
    val speakerOn: Boolean = true,
    val mode: TalkMode = TalkMode.Auto,
    val pttHeld: Boolean = false,
    val scam: ScamState? = null,
    /** A non-fatal problem the server reported, shown briefly. */
    val notice: String? = null,
    val endReason: EndReason? = null,
    val endDetail: String? = null,
    val elapsedSec: Int = 0,
) {
    val isActive: Boolean
        get() = phase != Phase.Idle && phase != Phase.Ended
}

/** What the UI and view models see. Implemented by [CallSession]. */
interface CallController {
    val state: StateFlow<CallUiState>
    fun setMuted(muted: Boolean)
    fun setSpeaker(on: Boolean)
    fun setMode(mode: TalkMode)
    fun pttPressed(down: Boolean)
    fun dismissScam()
    fun hangUp()
}

/** Lets the join screen hand over connection details without knowing about the session. */
interface CallStarter {
    fun prepare(params: CallParams)
}

const val MAX_TRANSCRIPT_ITEMS = 100

/** Pure state change for a server message. Side effects (haptics, audio) live in the session. */
fun CallUiState.reduce(msg: ServerMessage): CallUiState = when (msg) {
    is ServerMessage.Joined -> copy(
        phase = if (msg.peer != null) Phase.InCall else Phase.Waiting,
        peer = msg.peer,
        notice = null,
    )
    is ServerMessage.PeerJoined -> copy(
        phase = Phase.InCall,
        peer = PeerInfo(msg.name, msg.language),
    )
    is ServerMessage.PeerLeft -> copy(
        phase = Phase.Waiting,
        peer = null,
        peerSpeaking = false,
        pttHeld = false,
    )
    is ServerMessage.Transcript -> copy(
        transcript = (
            transcript + TranscriptItem(
                utteranceId = msg.utteranceId,
                speaker = msg.speaker,
                original = msg.original,
                translated = msg.translated,
                tone = msg.tone,
            )
            ).takeLast(MAX_TRANSCRIPT_ITEMS),
        tone = if (msg.speaker == Speaker.Peer) msg.tone else tone,
    )
    is ServerMessage.Latency -> copy(
        lastLatencyMs = msg.totalMs,
        transcript = transcript.map {
            if (it.utteranceId == msg.utteranceId) it.copy(latencyMs = msg.totalMs) else it
        },
    )
    is ServerMessage.TtsStart -> copy(peerSpeaking = true)
    is ServerMessage.TtsEnd -> copy(peerSpeaking = false)
    is ServerMessage.ScamAlert -> copy(
        scam = if (msg.level == ScamLevel.None) {
            null
        } else {
            val old = scam
            val same = old != null && old.level == msg.level && old.category == msg.category
            ScamState(msg.level, msg.risk, msg.category, msg.reasons, dismissed = same && old!!.dismissed)
        },
    )
    is ServerMessage.Error ->
        if (msg.fatal) {
            copy(phase = Phase.Ended, endReason = EndReason.ServerError, endDetail = msg.message)
        } else {
            copy(notice = msg.message)
        }
    ServerMessage.Pong, is ServerMessage.Unknown -> this
}
