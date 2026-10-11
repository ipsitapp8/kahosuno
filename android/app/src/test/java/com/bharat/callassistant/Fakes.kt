package com.bharat.callassistant

import com.bharat.callassistant.call.CallController
import com.bharat.callassistant.call.CallParams
import com.bharat.callassistant.call.CallStarter
import com.bharat.callassistant.call.CallUiState
import com.bharat.callassistant.core.audio.AudioRoute
import com.bharat.callassistant.core.audio.Haptics
import com.bharat.callassistant.core.audio.MicSource
import com.bharat.callassistant.core.audio.SpeechPlayer
import com.bharat.callassistant.core.network.Connection
import com.bharat.callassistant.core.network.RoomApi
import com.bharat.callassistant.core.network.RoomTicket
import com.bharat.callassistant.core.network.Transport
import com.bharat.callassistant.core.network.TransportEvent
import com.bharat.callassistant.core.protocol.ScamLevel
import com.bharat.callassistant.core.protocol.TalkMode
import com.bharat.callassistant.history.HistoryEntry
import com.bharat.callassistant.history.HistoryRepository
import com.bharat.callassistant.settings.AppSettings
import com.bharat.callassistant.settings.SettingsStore
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.update
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

class FakeConnection(val url: String, private val onEvent: (TransportEvent) -> Unit) : Connection {
    val texts = mutableListOf<String>()
    val binaries = mutableListOf<ByteArray>()
    var closed = false

    override fun sendText(text: String): Boolean {
        texts += text
        return true
    }

    override fun sendBinary(bytes: ByteArray): Boolean {
        binaries += bytes
        return true
    }

    override fun close() {
        closed = true
    }

    fun emit(event: TransportEvent) = onEvent(event)
    fun emitText(json: String) = onEvent(TransportEvent.Text(json))

    /** Types of the JSON messages sent so far. */
    fun sentTypes(): List<String> = texts.map { it.json()["type"]!!.jsonPrimitive.content }
}

class FakeTransport : Transport {
    val connections = mutableListOf<FakeConnection>()
    val last: FakeConnection get() = connections.last()

    override fun open(url: String, onEvent: (TransportEvent) -> Unit): Connection =
        FakeConnection(url, onEvent).also { connections += it }
}

class FakeMic : MicSource {
    private val channel = Channel<ByteArray>(Channel.UNLIMITED)
    var failWith: Exception? = null

    fun push(frame: ByteArray) {
        channel.trySend(frame)
    }

    override fun frames(): Flow<ByteArray> {
        failWith?.let { error -> return kotlinx.coroutines.flow.flow { throw error } }
        return channel.receiveAsFlow()
    }
}

class FakePlayer : SpeechPlayer {
    val enqueued = mutableListOf<ByteArray>()
    var started = false
    var stopped = false
    var playing = false

    override fun start() {
        started = true
    }

    override fun enqueue(pcm: ByteArray) {
        enqueued += pcm
    }

    override fun stop() {
        stopped = true
    }

    override fun isPlaying() = playing
}

class FakeRoute : AudioRoute {
    var started = false
    var stopped = false
    val speakerCalls = mutableListOf<Boolean>()

    override fun start(speakerOn: Boolean) {
        started = true
        speakerCalls += speakerOn
    }

    override fun setSpeaker(on: Boolean) {
        speakerCalls += on
    }

    override fun stop() {
        stopped = true
    }
}

class FakeHaptics : Haptics {
    val warnings = mutableListOf<ScamLevel>()

    override fun warn(level: ScamLevel) {
        warnings += level
    }
}

class FakeHistory : HistoryRepository {
    val saved = mutableListOf<HistoryEntry>()

    override fun entries(): Flow<List<HistoryEntry>> = MutableStateFlow(saved.toList())

    override suspend fun add(entry: HistoryEntry) {
        saved += entry
    }

    override suspend fun clear() = saved.clear()
}

class FakeSettings(initial: AppSettings = AppSettings()) : SettingsStore {
    private val flow = MutableStateFlow(initial)
    override val settings: Flow<AppSettings> = flow

    override suspend fun update(transform: (AppSettings) -> AppSettings) = flow.update(transform)

    val value: AppSettings get() = flow.value
}

class FakeRoomApi : RoomApi {
    var failure: Exception? = null
    val calls = mutableListOf<String>()
    var ticket = RoomTicket(roomId = "room-1", code = "123456", token = "tok-1")

    override suspend fun createRoom(baseUrl: String, name: String, language: String): RoomTicket {
        calls += "create|$baseUrl|$name|$language"
        failure?.let { throw it }
        return ticket
    }

    override suspend fun joinRoom(
        baseUrl: String,
        code: String,
        name: String,
        language: String,
    ): RoomTicket {
        calls += "join|$baseUrl|$code|$name|$language"
        failure?.let { throw it }
        return ticket
    }
}

class FakeStarter : CallStarter {
    var prepared: CallParams? = null
    override fun prepare(params: CallParams) {
        prepared = params
    }
}

class FakeController : CallController {
    private val _state = MutableStateFlow(CallUiState())
    override val state: StateFlow<CallUiState> = _state.asStateFlow()
    val log = mutableListOf<String>()

    fun set(state: CallUiState) {
        _state.value = state
    }

    override fun setMuted(muted: Boolean) {
        log += "muted=$muted"
    }

    override fun setSpeaker(on: Boolean) {
        log += "speaker=$on"
    }

    override fun setMode(mode: TalkMode) {
        log += "mode=${mode.wire}"
    }

    override fun pttPressed(down: Boolean) {
        log += "ptt=$down"
    }

    override fun dismissScam() {
        log += "dismiss"
    }

    override fun hangUp() {
        log += "hangUp"
    }
}

fun String.json(): JsonObject = Json.parseToJsonElement(this).jsonObject

// ---- server message builders (the same shapes the backend sends) ----
fun joinedJson(peerName: String? = null, peerLang: String = "hi-IN"): String {
    val peer = if (peerName == null) "null" else """{"name":"$peerName","language":"$peerLang"}"""
    return """{"v":1,"type":"joined","participant_id":"p1","peer":$peer}"""
}

fun peerJoinedJson(name: String = "Sita", lang: String = "hi-IN") =
    """{"v":1,"type":"peer_joined","name":"$name","language":"$lang"}"""

fun peerLeftJson(name: String = "Sita", lang: String = "hi-IN") =
    """{"v":1,"type":"peer_left","name":"$name","language":"$lang"}"""

fun transcriptJson(
    id: String = "u1",
    speaker: String = "peer",
    original: String = "नमस्ते",
    translated: String = "ನಮಸ್ಕಾರ",
    tone: String = "calm",
) = """{"v":1,"type":"transcript","utterance_id":"$id","speaker":"$speaker","original":"$original","translated":"$translated","tone":"$tone"}"""

fun latencyJson(id: String = "u1", total: Int = 1800) =
    """{"v":1,"type":"latency","utterance_id":"$id","stt_ms":300,"translate_ms":1100,"tts_ms":240,"total_ms":$total}"""

fun scamJson(level: String, risk: Int = 80, category: String = "credential_request") =
    """{"v":1,"type":"scam_alert","level":"$level","risk":$risk,"category":"$category","reasons_hinglish":["OTP mat do."]}"""

fun errorJson(code: String, fatal: Boolean, message: String = "boom") =
    """{"v":1,"type":"error","code":"$code","message":"$message","fatal":$fatal}"""
