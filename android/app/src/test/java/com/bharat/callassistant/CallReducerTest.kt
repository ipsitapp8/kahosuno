package com.bharat.callassistant

import com.bharat.callassistant.call.CallUiState
import com.bharat.callassistant.call.EndReason
import com.bharat.callassistant.call.MAX_TRANSCRIPT_ITEMS
import com.bharat.callassistant.call.Phase
import com.bharat.callassistant.call.reduce
import com.bharat.callassistant.core.protocol.PeerInfo
import com.bharat.callassistant.core.protocol.Protocol
import com.bharat.callassistant.core.protocol.ScamLevel
import com.bharat.callassistant.core.protocol.ServerMessage
import com.bharat.callassistant.core.protocol.Speaker
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class CallReducerTest {
    private fun CallUiState.applyJson(json: String) = reduce(Protocol.parse(json))
    private val connecting = CallUiState(phase = Phase.Connecting)

    @Test
    fun `joined alone waits, joined with peer is in call`() {
        val waiting = connecting.applyJson(joinedJson())
        assertEquals(Phase.Waiting, waiting.phase)
        assertNull(waiting.peer)

        val inCall = connecting.applyJson(joinedJson("Sita"))
        assertEquals(Phase.InCall, inCall.phase)
        assertEquals(PeerInfo("Sita", "hi-IN"), inCall.peer)
    }

    @Test
    fun `peer joining and leaving moves between waiting and in call`() {
        val inCall = connecting.applyJson(joinedJson()).applyJson(peerJoinedJson("Sita"))
        assertEquals(Phase.InCall, inCall.phase)
        assertEquals("Sita", inCall.peer?.name)

        val left = inCall.copy(peerSpeaking = true, pttHeld = true).applyJson(peerLeftJson())
        assertEquals(Phase.Waiting, left.phase)
        assertNull(left.peer)
        assertFalse(left.peerSpeaking)
        assertFalse(left.pttHeld)
    }

    @Test
    fun `transcript is appended and the tone follows the other person only`() {
        var s = connecting.applyJson(transcriptJson("u1", "peer", tone = "angry"))
        assertEquals("angry", s.tone)
        s = s.applyJson(transcriptJson("u2", "self", tone = "excited"))
        assertEquals("angry", s.tone) // my own tone does not change the chip
        assertEquals(listOf(Speaker.Peer, Speaker.Self), s.transcript.map { it.speaker })
    }

    @Test
    fun `latency updates the indicator and the matching bubble`() {
        val s = connecting
            .applyJson(transcriptJson("u1", "peer"))
            .applyJson(transcriptJson("u2", "peer"))
            .applyJson(latencyJson("u1", 1700))
        assertEquals(1700, s.lastLatencyMs)
        assertEquals(1700, s.transcript[0].latencyMs)
        assertNull(s.transcript[1].latencyMs)
    }

    @Test
    fun `the same utterance heard by both sides gets distinct keys`() {
        val s = connecting.applyJson(transcriptJson("u1", "self")).applyJson(transcriptJson("u1", "peer"))
        assertEquals(2, s.transcript.map { it.key }.toSet().size)
    }

    @Test
    fun `transcript is capped`() {
        var s = connecting
        repeat(MAX_TRANSCRIPT_ITEMS + 20) { s = s.applyJson(transcriptJson("u$it", "peer")) }
        assertEquals(MAX_TRANSCRIPT_ITEMS, s.transcript.size)
        assertEquals("u${MAX_TRANSCRIPT_ITEMS + 19}", s.transcript.last().utteranceId)
    }

    @Test
    fun `tts start and end toggle the speaking flag`() {
        val s = connecting.reduce(ServerMessage.TtsStart("u1"))
        assertTrue(s.peerSpeaking)
        assertFalse(s.reduce(ServerMessage.TtsEnd("u1")).peerSpeaking)
    }

    @Test
    fun `scam alert sets and clears the banner`() {
        val high = connecting.applyJson(scamJson("high", 85, "credential_request"))
        assertEquals(ScamLevel.High, high.scam?.level)
        assertEquals(85, high.scam?.risk)
        assertFalse(high.scam!!.dismissed)
        assertNull(high.applyJson(scamJson("none", 0, "none")).scam)
    }

    @Test
    fun `dismissed banner stays dismissed for repeats but returns when it gets worse`() {
        val dismissed = connecting.applyJson(scamJson("suspicious", 50, "kyc"))
            .let { it.copy(scam = it.scam!!.copy(dismissed = true)) }
        // same level and category again: still dismissed
        assertTrue(dismissed.applyJson(scamJson("suspicious", 55, "kyc")).scam!!.dismissed)
        // worse: show it again
        assertFalse(dismissed.applyJson(scamJson("high", 90, "credential_request")).scam!!.dismissed)
    }

    @Test
    fun `non fatal error is a notice, fatal error ends the call`() {
        val notice = connecting.applyJson(errorJson("upstream_failed", false, "try again"))
        assertEquals("try again", notice.notice)
        assertEquals(Phase.Connecting, notice.phase)

        val fatal = connecting.applyJson(errorJson("room_not_found", true, "gone"))
        assertEquals(Phase.Ended, fatal.phase)
        assertEquals(EndReason.ServerError, fatal.endReason)
        assertEquals("gone", fatal.endDetail)
    }

    @Test
    fun `pong and unknown messages change nothing`() {
        assertEquals(connecting, connecting.reduce(ServerMessage.Pong))
        assertEquals(connecting, connecting.reduce(ServerMessage.Unknown("x")))
    }
}
