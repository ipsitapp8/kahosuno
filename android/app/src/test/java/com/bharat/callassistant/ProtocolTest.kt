package com.bharat.callassistant

import com.bharat.callassistant.core.network.DEFAULT_SERVER_URL
import com.bharat.callassistant.core.network.normalizeBaseUrl
import com.bharat.callassistant.core.network.webSocketUrl
import com.bharat.callassistant.core.protocol.AUDIO_IN
import com.bharat.callassistant.core.protocol.AUDIO_OUT
import com.bharat.callassistant.core.protocol.PeerInfo
import com.bharat.callassistant.core.protocol.Protocol
import com.bharat.callassistant.core.protocol.ScamLevel
import com.bharat.callassistant.core.protocol.ServerMessage
import com.bharat.callassistant.core.protocol.Speaker
import com.bharat.callassistant.core.protocol.TalkMode
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ProtocolTest {

    @Test
    fun `joined with and without a peer`() {
        val alone = Protocol.parse(joinedJson())
        assertEquals(ServerMessage.Joined("p1", null), alone)
        val withPeer = Protocol.parse(joinedJson("Sita", "hi-IN"))
        assertEquals(ServerMessage.Joined("p1", PeerInfo("Sita", "hi-IN")), withPeer)
    }

    @Test
    fun `peer joined and left`() {
        assertEquals(ServerMessage.PeerJoined("Sita", "hi-IN"), Protocol.parse(peerJoinedJson()))
        assertEquals(ServerMessage.PeerLeft("Sita", "hi-IN"), Protocol.parse(peerLeftJson()))
    }

    @Test
    fun `transcript keeps unicode and maps speaker`() {
        val msg = Protocol.parse(transcriptJson(speaker = "self", tone = "excited")) as ServerMessage.Transcript
        assertEquals(Speaker.Self, msg.speaker)
        assertEquals("नमस्ते", msg.original)
        assertEquals("ನಮಸ್ಕಾರ", msg.translated)
        assertEquals("excited", msg.tone)
        assertEquals(Speaker.Peer, (Protocol.parse(transcriptJson(speaker = "peer")) as ServerMessage.Transcript).speaker)
    }

    @Test
    fun `transcript without tone defaults to calm`() {
        val msg = Protocol.parse(
            """{"type":"transcript","utterance_id":"u","speaker":"peer","original":"a","translated":"b"}""",
        ) as ServerMessage.Transcript
        assertEquals("calm", msg.tone)
    }

    @Test
    fun `latency fields`() {
        assertEquals(
            ServerMessage.Latency("u1", 300, 1100, 240, 1800),
            Protocol.parse(latencyJson()),
        )
    }

    @Test
    fun `scam alert levels and reasons`() {
        val high = Protocol.parse(scamJson("high")) as ServerMessage.ScamAlert
        assertEquals(ScamLevel.High, high.level)
        assertEquals(80, high.risk)
        assertEquals(listOf("OTP mat do."), high.reasons)
        assertEquals(
            ScamLevel.Suspicious,
            (Protocol.parse(scamJson("suspicious")) as ServerMessage.ScamAlert).level,
        )
        assertEquals(ScamLevel.None, (Protocol.parse(scamJson("none")) as ServerMessage.ScamAlert).level)
    }

    @Test
    fun `error fatal flag defaults to false`() {
        assertEquals(ServerMessage.Error("x", "m", true), Protocol.parse(errorJson("x", true, "m")))
        val msg = Protocol.parse("""{"type":"error","code":"x","message":"m"}""") as ServerMessage.Error
        assertFalse(msg.fatal)
    }

    @Test
    fun `simple messages`() {
        assertEquals(ServerMessage.Pong, Protocol.parse("""{"v":1,"type":"pong"}"""))
        assertEquals(ServerMessage.TtsStart("u9"), Protocol.parse("""{"type":"tts_start","utterance_id":"u9"}"""))
        assertEquals(ServerMessage.TtsEnd("u9"), Protocol.parse("""{"type":"tts_end","utterance_id":"u9"}"""))
    }

    @Test
    fun `unknown types and garbage never throw`() {
        assertTrue(Protocol.parse("""{"type":"from_the_future","x":1}""") is ServerMessage.Unknown)
        assertTrue(Protocol.parse("not json at all") is ServerMessage.Unknown)
        assertTrue(Protocol.parse("[1,2,3]") is ServerMessage.Unknown)
        assertTrue(Protocol.parse("") is ServerMessage.Unknown)
    }

    @Test
    fun `extra unknown fields are ignored`() {
        assertEquals(
            ServerMessage.PeerJoined("A", "kn-IN"),
            Protocol.parse("""{"type":"peer_joined","name":"A","language":"kn-IN","new_field":{"a":1}}"""),
        )
    }

    @Test
    fun `hello message`() {
        val obj = Protocol.hello("Ramesh", "kn-IN", TalkMode.PushToTalk).json()
        assertEquals("hello", obj["type"]!!.jsonPrimitive.content)
        assertEquals(1, obj["v"]!!.jsonPrimitive.int)
        assertEquals("Ramesh", obj["name"]!!.jsonPrimitive.content)
        assertEquals("kn-IN", obj["language"]!!.jsonPrimitive.content)
        assertTrue(obj["consent"]!!.jsonPrimitive.boolean)
        assertEquals("ptt", obj["mode"]!!.jsonPrimitive.content)
        assertFalse(obj["store_transcript"]!!.jsonPrimitive.boolean)
    }

    @Test
    fun `hello keeps non-ascii names intact`() {
        val obj = Protocol.hello("ರಮೇಶ್", "kn-IN", TalkMode.Auto).json()
        assertEquals("ರಮೇಶ್", obj["name"]!!.jsonPrimitive.content)
    }

    @Test
    fun `control messages carry the right type`() {
        fun type(s: String) = s.json()["type"]!!.jsonPrimitive.content
        assertEquals("ping", type(Protocol.ping()))
        assertEquals("bye", type(Protocol.bye()))
        assertEquals("ptt_start", type(Protocol.pttStart()))
        assertEquals("ptt_end", type(Protocol.pttEnd()))
        assertEquals("mode", type(Protocol.mode(TalkMode.Auto)))
        assertEquals("auto", Protocol.mode(TalkMode.Auto).json()["mode"]!!.jsonPrimitive.content)
    }

    @Test
    fun `mic frames are prefixed with the audio type`() {
        val pcm = byteArrayOf(1, 2, 3, 4)
        val frame = Protocol.micFrame(pcm)
        assertEquals(AUDIO_IN, frame[0])
        assertArrayEquals(pcm, frame.copyOfRange(1, frame.size))
    }

    @Test
    fun `speech frames are unwrapped and other frames rejected`() {
        val pcm = byteArrayOf(9, 8, 7)
        assertArrayEquals(pcm, Protocol.speechPcm(byteArrayOf(AUDIO_OUT, 9, 8, 7)))
        assertNull(Protocol.speechPcm(byteArrayOf(AUDIO_IN, 1, 2)))
        assertNull(Protocol.speechPcm(byteArrayOf(AUDIO_OUT))) // header only
        assertNull(Protocol.speechPcm(byteArrayOf()))
    }

    @Test
    fun `talk mode wire names`() {
        assertEquals(TalkMode.Auto, TalkMode.fromWire("auto"))
        assertEquals(TalkMode.PushToTalk, TalkMode.fromWire("ptt"))
        assertEquals(TalkMode.Auto, TalkMode.fromWire("nonsense"))
        assertEquals(TalkMode.Auto, TalkMode.fromWire(null))
    }

    // ---- URLs ----
    @Test
    fun `base url is cleaned up`() {
        assertEquals("https://app.onrender.com", normalizeBaseUrl("  https://app.onrender.com/  "))
        assertEquals("https://app.onrender.com", normalizeBaseUrl("app.onrender.com"))
        assertEquals("http://10.0.2.2:8000", normalizeBaseUrl("10.0.2.2:8000"))
        assertEquals("http://localhost:8000", normalizeBaseUrl("localhost:8000"))
        assertEquals(DEFAULT_SERVER_URL, normalizeBaseUrl("   "))
    }

    @Test
    fun `websocket url switches scheme and encodes token`() {
        assertEquals(
            "ws://10.0.2.2:8000/ws/v1/rooms/r1?token=a.b",
            webSocketUrl("http://10.0.2.2:8000", "r1", "a.b"),
        )
        assertEquals(
            "wss://app.onrender.com/ws/v1/rooms/r1?token=a%2Bb",
            webSocketUrl("https://app.onrender.com/", "r1", "a+b"),
        )
    }
}
