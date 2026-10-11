package com.bharat.callassistant

import com.bharat.callassistant.call.CallParams
import com.bharat.callassistant.call.CallSession
import com.bharat.callassistant.call.EndReason
import com.bharat.callassistant.call.PING_INTERVAL_MS
import com.bharat.callassistant.call.Phase
import com.bharat.callassistant.core.network.TransportEvent
import com.bharat.callassistant.core.protocol.AUDIO_IN
import com.bharat.callassistant.core.protocol.AUDIO_OUT
import com.bharat.callassistant.core.protocol.FRAME_BYTES
import com.bharat.callassistant.core.protocol.ScamLevel
import com.bharat.callassistant.core.protocol.TalkMode
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

@OptIn(ExperimentalCoroutinesApi::class)
class CallSessionTest {

    private class Harness(scope: TestScope, backoff: List<Long> = listOf(1_000L, 2_000L)) {
        val transport = FakeTransport()
        val mic = FakeMic()
        val player = FakePlayer()
        val route = FakeRoute()
        val haptics = FakeHaptics()
        val history = FakeHistory()
        val session = CallSession(
            transport = transport,
            mic = mic,
            player = player,
            route = route,
            haptics = haptics,
            history = history,
            scope = scope.backgroundScope,
            clock = { scope.testScheduler.currentTime },
            backoffMs = backoff,
        )
        val params = CallParams(
            serverUrl = "http://10.0.2.2:8000",
            roomId = "room1",
            code = "123456",
            token = "tok",
            name = "Ramesh",
            language = "kn-IN",
            mode = TalkMode.Auto,
        )

        val state get() = session.state.value
        val conn get() = transport.last

        fun begin(mode: TalkMode = TalkMode.Auto) {
            session.prepare(params.copy(mode = mode))
            session.start()
        }

        /** Open, send hello, and have the server accept us (alone, or with a peer). */
        fun connect(peer: String? = null) {
            conn.emit(TransportEvent.Opened)
            conn.emitText(joinedJson(peer))
        }
    }

    private fun frame(fill: Int = 7) = ByteArray(FRAME_BYTES) { fill.toByte() }

    @Test
    fun `start opens the right url, sets up audio and says hello`() = runTest {
        val h = Harness(this)
        h.begin()
        runCurrent()

        assertEquals(1, h.transport.connections.size)
        assertEquals("ws://10.0.2.2:8000/ws/v1/rooms/room1?token=tok", h.conn.url)
        assertTrue(h.route.started && h.player.started)
        assertEquals(Phase.Connecting, h.state.phase)

        h.conn.emit(TransportEvent.Opened)
        runCurrent()
        val hello = h.conn.texts.single().json()
        assertEquals("hello", hello["type"]!!.jsonPrimitive.content)
        assertEquals("Ramesh", hello["name"]!!.jsonPrimitive.content)
        assertEquals("kn-IN", hello["language"]!!.jsonPrimitive.content)
        assertEquals("auto", hello["mode"]!!.jsonPrimitive.content)
    }

    @Test
    fun `joined alone waits, then a peer arrives`() = runTest {
        val h = Harness(this)
        h.begin()
        runCurrent()
        h.connect()
        runCurrent()
        assertEquals(Phase.Waiting, h.state.phase)

        h.conn.emitText(peerJoinedJson("Sita", "hi-IN"))
        runCurrent()
        assertEquals(Phase.InCall, h.state.phase)
        assertEquals("Sita", h.state.peer?.name)
    }

    @Test
    fun `transcripts and latency reach the state`() = runTest {
        val h = Harness(this)
        h.begin()
        runCurrent()
        h.connect("Sita")
        h.conn.emitText(transcriptJson("u1", "peer", tone = "sad"))
        h.conn.emitText(latencyJson("u1", 1650))
        runCurrent()
        assertEquals(1, h.state.transcript.size)
        assertEquals("sad", h.state.tone)
        assertEquals(1650, h.state.lastLatencyMs)
    }

    // ---- microphone ----
    @Test
    fun `mic audio is sent as type 1 frames only after the server accepted us`() = runTest {
        val h = Harness(this)
        h.begin()
        runCurrent()
        h.conn.emit(TransportEvent.Opened)
        h.mic.push(frame(5))
        runCurrent()
        assertTrue("nothing before joined", h.conn.binaries.isEmpty())

        h.conn.emitText(joinedJson("Sita"))
        h.mic.push(frame(6))
        runCurrent()
        val sent = h.conn.binaries.single()
        assertEquals(AUDIO_IN, sent[0])
        assertEquals(FRAME_BYTES + 1, sent.size)
        assertArrayEquals(frame(6), sent.copyOfRange(1, sent.size))
    }

    @Test
    fun `muting sends silence instead of audio`() = runTest {
        val h = Harness(this)
        h.begin()
        runCurrent()
        h.connect("Sita")
        h.session.setMuted(true)
        h.mic.push(frame(9))
        runCurrent()
        val sent = h.conn.binaries.single()
        assertTrue(sent.copyOfRange(1, sent.size).all { it == 0.toByte() })
        assertEquals(FRAME_BYTES + 1, sent.size) // still a frame, so the server can end a sentence
    }

    @Test
    fun `mic is silenced while translated speech plays on the loudspeaker`() = runTest {
        val h = Harness(this)
        h.begin()
        runCurrent()
        h.connect("Sita")
        h.player.playing = true

        h.session.setSpeaker(true)
        h.mic.push(frame(9))
        runCurrent()
        assertTrue(h.conn.binaries.last().drop(1).all { it == 0.toByte() })

        h.session.setSpeaker(false) // earpiece: the phone cannot hear itself
        h.mic.push(frame(9))
        runCurrent()
        assertTrue(h.conn.binaries.last().drop(1).all { it == 9.toByte() })
    }

    @Test
    fun `push to talk sends audio only while the button is held`() = runTest {
        val h = Harness(this)
        h.begin(TalkMode.PushToTalk)
        runCurrent()
        h.connect("Sita")
        h.mic.push(frame())
        runCurrent()
        assertTrue(h.conn.binaries.isEmpty())

        h.session.pttPressed(true)
        h.mic.push(frame())
        runCurrent()
        assertEquals(1, h.conn.binaries.size)

        h.session.pttPressed(false)
        h.mic.push(frame())
        runCurrent()
        assertEquals(1, h.conn.binaries.size)
        assertEquals(listOf("hello", "ptt_start", "ptt_end"), h.conn.sentTypes())
    }

    @Test
    fun `ptt presses are ignored in auto mode, and switching mode tells the server`() = runTest {
        val h = Harness(this)
        h.begin()
        runCurrent()
        h.connect("Sita")
        runCurrent() // let the server's "joined" be handled
        h.session.pttPressed(true)
        assertFalse(h.state.pttHeld)
        assertEquals(listOf("hello"), h.conn.sentTypes()) // no ptt_start in auto mode

        h.session.setMode(TalkMode.PushToTalk)
        assertEquals(TalkMode.PushToTalk, h.state.mode)
        assertEquals("ptt", h.conn.texts.last().json()["mode"]!!.jsonPrimitive.content)
    }

    @Test
    fun `microphone failure ends the call with an audio error`() = runTest {
        val h = Harness(this)
        h.mic.failWith = IOException("Microphone could not be opened")
        h.begin()
        runCurrent()
        assertEquals(Phase.Ended, h.state.phase)
        assertEquals(EndReason.AudioError, h.state.endReason)
        assertEquals("Microphone could not be opened", h.state.endDetail)
        assertTrue(h.route.stopped && h.player.stopped)
    }

    // ---- speech playback ----
    @Test
    fun `speech frames are played, other binary frames ignored`() = runTest {
        val h = Harness(this)
        h.begin()
        runCurrent()
        h.connect("Sita")
        h.conn.emit(TransportEvent.Binary(byteArrayOf(AUDIO_OUT, 1, 2, 3)))
        h.conn.emit(TransportEvent.Binary(byteArrayOf(AUDIO_IN, 9, 9)))
        runCurrent()
        assertEquals(1, h.player.enqueued.size)
        assertArrayEquals(byteArrayOf(1, 2, 3), h.player.enqueued.single())
    }

    // ---- scam alerts ----
    @Test
    fun `scam alert shows the banner and vibrates once per escalation`() = runTest {
        val h = Harness(this)
        h.begin()
        runCurrent()
        h.connect("Sita")

        h.conn.emitText(scamJson("suspicious", 50, "kyc"))
        runCurrent()
        assertEquals(ScamLevel.Suspicious, h.state.scam?.level)
        assertEquals(listOf(ScamLevel.Suspicious), h.haptics.warnings)

        h.conn.emitText(scamJson("suspicious", 55, "kyc")) // repeat: no new buzz
        h.conn.emitText(scamJson("high", 90, "credential_request"))
        h.conn.emitText(scamJson("high", 92, "credential_request"))
        runCurrent()
        assertEquals(listOf(ScamLevel.Suspicious, ScamLevel.High), h.haptics.warnings)

        h.conn.emitText(scamJson("none", 0, "none"))
        runCurrent()
        assertEquals(null, h.state.scam)
        h.conn.emitText(scamJson("suspicious", 50, "kyc")) // a new episode buzzes again
        runCurrent()
        assertEquals(3, h.haptics.warnings.size)
    }

    @Test
    fun `dismissing hides the banner without ending the warning`() = runTest {
        val h = Harness(this)
        h.begin()
        runCurrent()
        h.connect("Sita")
        h.conn.emitText(scamJson("high"))
        runCurrent()
        h.session.dismissScam()
        assertTrue(h.state.scam!!.dismissed)
    }

    // ---- reconnecting ----
    @Test
    fun `a dropped connection reconnects with backoff and says hello again`() = runTest {
        val h = Harness(this)
        h.begin()
        runCurrent()
        h.connect("Sita")
        runCurrent()

        h.conn.emit(TransportEvent.Failed(IOException("reset")))
        runCurrent()
        assertEquals(Phase.Reconnecting, h.state.phase)
        assertEquals(1, h.transport.connections.size)

        advanceTimeBy(999)
        runCurrent()
        assertEquals(1, h.transport.connections.size)
        advanceTimeBy(2)
        runCurrent()
        assertEquals(2, h.transport.connections.size)

        h.conn.emit(TransportEvent.Opened)
        h.conn.emitText(joinedJson("Sita"))
        runCurrent()
        assertEquals(listOf("hello"), h.conn.sentTypes())
        assertEquals(Phase.InCall, h.state.phase)
    }

    @Test
    fun `no audio is sent while reconnecting`() = runTest {
        val h = Harness(this)
        h.begin()
        runCurrent()
        h.connect("Sita")
        runCurrent()
        val first = h.conn
        first.emit(TransportEvent.Closed(1006, "gone"))
        runCurrent()
        h.mic.push(frame())
        runCurrent()
        assertTrue(first.binaries.isEmpty())
    }

    @Test
    fun `backoff grows, and the call ends when attempts run out`() = runTest {
        val h = Harness(this, backoff = listOf(1_000L, 2_000L))
        h.begin()
        runCurrent()

        h.conn.emit(TransportEvent.Failed(IOException("down"))) // attempt 1 after 1 s
        runCurrent()
        advanceTimeBy(1_000)
        runCurrent()
        assertEquals(2, h.transport.connections.size)

        h.conn.emit(TransportEvent.Failed(IOException("down"))) // attempt 2 after 2 s
        runCurrent()
        advanceTimeBy(1_999)
        runCurrent()
        assertEquals(2, h.transport.connections.size)
        advanceTimeBy(1)
        runCurrent()
        assertEquals(3, h.transport.connections.size)

        h.conn.emit(TransportEvent.Failed(IOException("down"))) // out of attempts
        runCurrent()
        assertEquals(Phase.Ended, h.state.phase)
        assertEquals(EndReason.ConnectionLost, h.state.endReason)
    }

    @Test
    fun `a successful reconnect resets the backoff`() = runTest {
        val h = Harness(this, backoff = listOf(1_000L, 2_000L))
        h.begin()
        runCurrent()
        repeat(3) {
            h.conn.emit(TransportEvent.Failed(IOException("blip")))
            runCurrent()
            advanceTimeBy(1_000)
            runCurrent()
            h.conn.emit(TransportEvent.Opened) // the new connection works
            h.conn.emitText(joinedJson("Sita"))
            runCurrent()
        }
        assertEquals(Phase.InCall, h.state.phase)
        assertEquals(4, h.transport.connections.size)
    }

    @Test
    fun `events from an old connection are ignored`() = runTest {
        val h = Harness(this)
        h.begin()
        runCurrent()
        val old = h.conn
        old.emit(TransportEvent.Failed(IOException("x")))
        runCurrent()
        advanceTimeBy(1_000)
        runCurrent()
        assertEquals(2, h.transport.connections.size)

        old.emit(TransportEvent.Failed(IOException("late echo of the old socket")))
        runCurrent()
        advanceTimeBy(5_000)
        runCurrent()
        assertEquals("no extra reconnects", 2, h.transport.connections.size)
    }

    // ---- ending ----
    @Test
    fun `fatal server error ends the call without reconnecting`() = runTest {
        val h = Harness(this)
        h.begin()
        runCurrent()
        h.connect("Sita")
        h.conn.emitText(errorJson("consent_required", fatal = true, message = "No consent"))
        runCurrent()
        assertEquals(Phase.Ended, h.state.phase)
        assertEquals(EndReason.ServerError, h.state.endReason)
        assertEquals("No consent", h.state.endDetail)
        assertTrue(h.conn.closed)
        advanceTimeBy(60_000)
        runCurrent()
        assertEquals(1, h.transport.connections.size)
    }

    @Test
    fun `close code in the 44xx range is final`() = runTest {
        val h = Harness(this)
        h.begin()
        runCurrent()
        h.connect("Sita")
        h.conn.emit(TransportEvent.Closed(4404, "Room not found"))
        runCurrent()
        assertEquals(Phase.Ended, h.state.phase)
        assertEquals("Room not found", h.state.endDetail)
    }

    @Test
    fun `non fatal server error keeps the call alive`() = runTest {
        val h = Harness(this)
        h.begin()
        runCurrent()
        h.connect("Sita")
        h.conn.emitText(errorJson("upstream_failed", fatal = false, message = "try again"))
        runCurrent()
        assertEquals(Phase.InCall, h.state.phase)
        assertEquals("try again", h.state.notice)
    }

    @Test
    fun `hang up says bye, closes everything and saves metadata only`() = runTest {
        val h = Harness(this)
        h.begin()
        runCurrent()
        h.connect("Sita")
        h.conn.emitText(latencyJson("a", 1000))
        h.conn.emitText(latencyJson("b", 2000))
        h.conn.emitText(scamJson("high"))
        runCurrent()
        advanceTimeBy(65_000)
        runCurrent()

        h.session.hangUp()
        runCurrent()

        assertEquals(Phase.Ended, h.state.phase)
        assertEquals(EndReason.HangUp, h.state.endReason)
        assertEquals("bye", h.conn.sentTypes().last())
        assertTrue(h.conn.closed && h.player.stopped && h.route.stopped)

        val saved = h.history.saved.single()
        assertEquals("Sita", saved.peerName)
        assertEquals("hi-IN", saved.peerLanguage)
        assertEquals("kn-IN", saved.myLanguage)
        assertEquals("123456", saved.roomCode)
        assertEquals(1500, saved.avgLatencyMs)
        assertEquals("high", saved.maxScam)
        assertEquals(65, saved.durationSec)
    }

    @Test
    fun `a call that never connected leaves no history`() = runTest {
        val h = Harness(this)
        h.begin()
        runCurrent()
        h.session.hangUp()
        runCurrent()
        assertEquals(Phase.Ended, h.state.phase)
        assertTrue(h.history.saved.isEmpty())
    }

    @Test
    fun `hanging up twice is harmless`() = runTest {
        val h = Harness(this)
        h.begin()
        runCurrent()
        h.connect("Sita")
        runCurrent()
        h.session.hangUp()
        h.session.hangUp()
        runCurrent()
        assertEquals(1, h.history.saved.size)
    }

    @Test
    fun `peer leaving returns to waiting and history keeps their name`() = runTest {
        val h = Harness(this)
        h.begin()
        runCurrent()
        h.connect("Sita")
        h.conn.emitText(peerLeftJson("Sita"))
        runCurrent()
        assertEquals(Phase.Waiting, h.state.phase)
        h.session.hangUp()
        runCurrent()
        assertEquals("Sita", h.history.saved.single().peerName)
    }

    @Test
    fun `a second call can start after the first ended`() = runTest {
        val h = Harness(this)
        h.begin()
        runCurrent()
        h.connect("Sita")
        h.session.hangUp()
        runCurrent()

        h.begin()
        runCurrent()
        assertEquals(2, h.transport.connections.size)
        assertEquals(Phase.Connecting, h.state.phase)
        assertTrue(h.state.transcript.isEmpty())
        assertNotNull(h.conn)
    }

    // ---- housekeeping ----
    @Test
    fun `controls update the state, speaker changes the route`() = runTest {
        val h = Harness(this)
        h.begin()
        runCurrent()
        h.session.setSpeaker(false)
        h.session.setMuted(true)
        assertFalse(h.state.speakerOn)
        assertTrue(h.state.muted)
        assertEquals(listOf(true, false), h.route.speakerCalls)
    }

    @Test
    fun `keepalive ping is sent while connected, and the timer ticks`() = runTest {
        val h = Harness(this)
        h.begin()
        runCurrent()
        h.connect("Sita")
        runCurrent()
        advanceTimeBy(PING_INTERVAL_MS + 100)
        runCurrent()
        assertTrue("ping" in h.conn.sentTypes())
        assertEquals(15, h.state.elapsedSec)
    }
}
