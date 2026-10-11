package com.bharat.callassistant.call

import com.bharat.callassistant.core.audio.AudioRoute
import com.bharat.callassistant.core.audio.Haptics
import com.bharat.callassistant.core.audio.MicSource
import com.bharat.callassistant.core.audio.SpeechPlayer
import com.bharat.callassistant.core.network.Connection
import com.bharat.callassistant.core.network.Transport
import com.bharat.callassistant.core.network.TransportEvent
import com.bharat.callassistant.core.network.webSocketUrl
import com.bharat.callassistant.core.protocol.PeerInfo
import com.bharat.callassistant.core.protocol.Protocol
import com.bharat.callassistant.core.protocol.ScamLevel
import com.bharat.callassistant.core.protocol.ServerMessage
import com.bharat.callassistant.core.protocol.TalkMode
import com.bharat.callassistant.history.HistoryEntry
import com.bharat.callassistant.history.HistoryRepository
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

val DEFAULT_BACKOFF_MS = listOf(1_000L, 2_000L, 4_000L, 8_000L, 15_000L, 30_000L)
const val PING_INTERVAL_MS = 15_000L

/**
 * One call at a time. Owns the websocket, the microphone loop and the speech player, so the
 * call survives the screen turning off (it is driven by [CallService], not by a screen).
 *
 * Threading: transport events are queued and handled one by one on a single coroutine, so
 * the handling code does not need locks. UI calls only touch the state flow and send frames.
 */
class CallSession(
    private val transport: Transport,
    private val mic: MicSource,
    private val player: SpeechPlayer,
    private val route: AudioRoute,
    private val haptics: Haptics,
    private val history: HistoryRepository,
    private val scope: CoroutineScope,
    private val clock: () -> Long = System::currentTimeMillis,
    private val backoffMs: List<Long> = DEFAULT_BACKOFF_MS,
) : CallController, CallStarter {

    private val lock = Any()
    private val _state = MutableStateFlow(CallUiState())
    override val state: StateFlow<CallUiState> = _state.asStateFlow()

    private var params: CallParams? = null
    private var events = Channel<Pair<Int, TransportEvent>>(Channel.UNLIMITED)
    private val jobs = mutableListOf<Job>()
    private var reconnectJob: Job? = null

    @Volatile private var connection: Connection? = null
    @Volatile private var ready = false
    @Volatile private var generation = 0
    @Volatile private var running = false
    private var attempt = 0
    private var startedAt = 0L
    private var joinedOnce = false
    private var lastPeer: PeerInfo? = null
    private val latencies = mutableListOf<Int>()
    private var maxScam = ScamLevel.None
    private var hapticLevel = ScamLevel.None

    // ---- setup ----
    override fun prepare(params: CallParams) {
        synchronized(lock) {
            if (running) return // a call is already in progress
            this.params = params
            _state.value = CallUiState(
                phase = Phase.Connecting,
                roomCode = params.code,
                myName = params.name,
                myLanguage = params.language,
                mode = params.mode,
            )
            attempt = 0
            joinedOnce = false
            lastPeer = null
            latencies.clear()
            maxScam = ScamLevel.None
            hapticLevel = ScamLevel.None
        }
    }

    /** Called by the foreground service once it is running. */
    fun start() {
        val queue: Channel<Pair<Int, TransportEvent>>
        synchronized(lock) {
            if (running || params == null) return
            running = true
            startedAt = clock()
            queue = Channel(Channel.UNLIMITED)
            events = queue
        }
        route.start(_state.value.speakerOn)
        player.start()
        jobs += scope.launch {
            for ((gen, event) in queue) {
                if (gen == generation) handle(event)
            }
        }
        connect()
        jobs += scope.launch { captureLoop() }
        jobs += scope.launch { pingLoop() }
        jobs += scope.launch { tickLoop() }
    }

    private fun connect() {
        val p = params ?: return
        synchronized(lock) {
            val gen = ++generation
            val queue = events
            connection = transport.open(webSocketUrl(p.serverUrl, p.roomId, p.token)) { event ->
                queue.trySend(gen to event)
            }
        }
    }

    // ---- incoming events ----
    private fun handle(event: TransportEvent) {
        when (event) {
            TransportEvent.Opened -> {
                synchronized(lock) { /* wait until connect() has stored the connection */ }
                attempt = 0
                val p = params ?: return
                connection?.sendText(Protocol.hello(p.name, p.language, _state.value.mode))
            }
            is TransportEvent.Text -> onMessage(Protocol.parse(event.text))
            is TransportEvent.Binary -> Protocol.speechPcm(event.bytes)?.let(player::enqueue)
            is TransportEvent.Closed ->
                if (event.code in 4400..4499) {
                    end(EndReason.ServerError, event.reason.ifBlank { "closed (${event.code})" })
                } else {
                    onDisconnected()
                }
            is TransportEvent.Failed -> onDisconnected()
        }
    }

    private fun onMessage(msg: ServerMessage) {
        if (msg is ServerMessage.Error && msg.fatal) {
            end(EndReason.ServerError, msg.message)
            return
        }
        when (msg) {
            is ServerMessage.Joined -> {
                ready = true
                joinedOnce = true
            }
            is ServerMessage.Latency -> latencies += msg.totalMs
            is ServerMessage.ScamAlert -> onScam(msg.level)
            else -> Unit
        }
        _state.update { it.reduce(msg) }
        _state.value.peer?.let { lastPeer = it }
    }

    private fun onScam(level: ScamLevel) {
        if (level.ordinal > maxScam.ordinal) maxScam = level
        // Vibrate when the warning gets worse, not on every repeat of the same level.
        if (level == ScamLevel.None) {
            hapticLevel = ScamLevel.None
        } else if (level.ordinal > hapticLevel.ordinal) {
            hapticLevel = level
            haptics.warn(level)
        }
    }

    /** The socket dropped. Try again with growing delays, unless we are hanging up. */
    private fun onDisconnected() {
        if (!running) return
        connection = null
        ready = false
        _state.update { it.copy(phase = Phase.Reconnecting, peerSpeaking = false, pttHeld = false) }
        if (attempt >= backoffMs.size) {
            end(EndReason.ConnectionLost)
            return
        }
        val wait = backoffMs[attempt++]
        reconnectJob?.cancel()
        reconnectJob = scope.launch {
            delay(wait)
            if (running) connect()
        }
    }

    // ---- outgoing audio ----
    private suspend fun captureLoop() {
        try {
            mic.frames().collect { sendMic(it) }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            end(EndReason.AudioError, e.message)
        }
    }

    private fun sendMic(frame: ByteArray) {
        val conn = connection ?: return
        if (!ready) return
        val s = _state.value
        if (s.mode == TalkMode.PushToTalk && !s.pttHeld) return
        // Send silence (not nothing) while muted, so the server can close any open sentence.
        // Also stay quiet while the translated voice plays on the loudspeaker, otherwise the
        // phone would hear itself and translate its own translation.
        val gated = s.muted || (s.speakerOn && player.isPlaying())
        conn.sendBinary(Protocol.micFrame(if (gated) ByteArray(frame.size) else frame))
    }

    private suspend fun pingLoop() {
        while (scope.isActive) {
            delay(PING_INTERVAL_MS)
            if (ready) connection?.sendText(Protocol.ping())
        }
    }

    private suspend fun tickLoop() {
        while (scope.isActive) {
            delay(1_000)
            val seconds = ((clock() - startedAt) / 1000).toInt()
            _state.update { it.copy(elapsedSec = seconds) }
        }
    }

    // ---- controls ----
    override fun setMuted(muted: Boolean) = _state.update { it.copy(muted = muted) }

    override fun setSpeaker(on: Boolean) {
        _state.update { it.copy(speakerOn = on) }
        if (running) route.setSpeaker(on)
    }

    override fun setMode(mode: TalkMode) {
        _state.update { it.copy(mode = mode, pttHeld = false) }
        if (ready) connection?.sendText(Protocol.mode(mode))
    }

    override fun pttPressed(down: Boolean) {
        val s = _state.value
        if (s.mode != TalkMode.PushToTalk || !ready || s.pttHeld == down) return
        _state.update { it.copy(pttHeld = down) }
        connection?.sendText(if (down) Protocol.pttStart() else Protocol.pttEnd())
    }

    override fun dismissScam() = _state.update { s ->
        s.copy(scam = s.scam?.copy(dismissed = true))
    }

    override fun hangUp() {
        connection?.sendText(Protocol.bye())
        end(EndReason.HangUp)
    }

    // ---- teardown ----
    private fun end(reason: EndReason, detail: String? = null) {
        val snapshot: CallUiState
        synchronized(lock) {
            if (!running) return
            running = false
            reconnectJob?.cancel()
            jobs.forEach { it.cancel() }
            jobs.clear()
            connection?.close()
            connection = null
            ready = false
            events.close()
            player.stop()
            route.stop()
            _state.update {
                it.copy(
                    phase = Phase.Ended,
                    endReason = reason,
                    endDetail = detail,
                    peerSpeaking = false,
                    pttHeld = false,
                )
            }
            snapshot = _state.value
        }
        saveHistory(snapshot)
    }

    private fun saveHistory(snapshot: CallUiState) {
        if (!joinedOnce) return // never actually connected: nothing worth keeping
        val entry = HistoryEntry(
            startedAt = startedAt,
            durationSec = ((clock() - startedAt) / 1000).toInt(),
            roomCode = snapshot.roomCode,
            peerName = lastPeer?.name.orEmpty(),
            myLanguage = snapshot.myLanguage,
            peerLanguage = lastPeer?.language.orEmpty(),
            avgLatencyMs = if (latencies.isEmpty()) 0 else latencies.average().toInt(),
            maxScam = maxScam.name.lowercase(),
        )
        scope.launch { runCatching { history.add(entry) } }
    }
}
