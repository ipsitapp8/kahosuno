package com.bharat.callassistant

import com.bharat.callassistant.core.network.ApiException
import com.bharat.callassistant.core.network.HttpRoomApi
import com.bharat.callassistant.core.network.RoomTicket
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test

class RoomApiTest {
    private lateinit var server: MockWebServer
    private lateinit var api: HttpRoomApi
    private lateinit var base: String

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        base = server.url("/").toString() // ends with a slash on purpose
        api = HttpRoomApi(OkHttpClient())
    }

    @After
    fun tearDown() {
        runCatching { server.shutdown() }
    }

    private val okBody = """{"room_id":"r1","code":"123456","token":"jwt.token.here"}"""

    private suspend fun failure(block: suspend () -> Unit): ApiException {
        try {
            block()
        } catch (e: ApiException) {
            return e
        }
        fail("expected an ApiException")
        throw IllegalStateException()
    }

    @Test
    fun `create room posts the right body and parses the ticket`() = runTest {
        server.enqueue(MockResponse().setBody(okBody))
        val ticket = api.createRoom(base, "ರಮೇಶ್", "kn-IN")
        assertEquals(RoomTicket("r1", "123456", "jwt.token.here"), ticket)

        val req = server.takeRequest()
        assertEquals("POST", req.method)
        assertEquals("/rooms", req.path)
        assertTrue(req.getHeader("Content-Type")!!.startsWith("application/json"))
        val body = req.body.readUtf8().json()
        assertEquals("ರಮೇಶ್", body["name"]!!.jsonPrimitive.content)
        assertEquals("kn-IN", body["language"]!!.jsonPrimitive.content)
        assertEquals("true", body["consent"]!!.jsonPrimitive.content)
    }

    @Test
    fun `join room uses the code in the path`() = runTest {
        server.enqueue(MockResponse().setBody(okBody))
        api.joinRoom(base, "654321", "Sita", "hi-IN")
        assertEquals("/rooms/654321/join", server.takeRequest().path)
    }

    @Test
    fun `server errors become typed exceptions`() = runTest {
        server.enqueue(
            MockResponse().setResponseCode(409)
                .setBody("""{"detail":{"code":"room_full","message":"Room already has two participants"}}"""),
        )
        val e = failure { api.joinRoom(base, "111111", "A", "hi-IN") }
        assertEquals("room_full", e.code)
        assertEquals("Room already has two participants", e.message)
        assertFalse(e.isNetwork)
    }

    @Test
    fun `404 unknown room and 429 rate limit`() = runTest {
        server.enqueue(
            MockResponse().setResponseCode(404)
                .setBody("""{"detail":{"code":"room_not_found","message":"Room not found"}}"""),
        )
        assertEquals("room_not_found", failure { api.joinRoom(base, "000000", "A", "hi-IN") }.code)

        server.enqueue(
            MockResponse().setResponseCode(429)
                .setBody("""{"detail":{"code":"rate_limited","message":"Too many requests"}}"""),
        )
        assertEquals("rate_limited", failure { api.createRoom(base, "A", "hi-IN") }.code)
    }

    @Test
    fun `validation errors and unexpected bodies are handled`() = runTest {
        server.enqueue(MockResponse().setResponseCode(422).setBody("""{"detail":[{"loc":["body"],"msg":"bad"}]}"""))
        assertEquals("bad_request", failure { api.createRoom(base, "A", "hi-IN") }.code)

        server.enqueue(MockResponse().setResponseCode(502).setBody("<html>Bad gateway</html>"))
        assertEquals("http_502", failure { api.createRoom(base, "A", "hi-IN") }.code)
    }

    @Test
    fun `a success reply that is not json is a bad_response`() = runTest {
        server.enqueue(MockResponse().setBody("<html>hello</html>"))
        assertEquals("bad_response", failure { api.createRoom(base, "A", "hi-IN") }.code)
    }

    @Test
    fun `a success reply missing fields is a bad_response`() = runTest {
        server.enqueue(MockResponse().setBody("""{"room_id":"r1"}"""))
        assertEquals("bad_response", failure { api.createRoom(base, "A", "hi-IN") }.code)
    }

    @Test
    fun `unreachable server is a network error`() = runTest {
        val dead = base
        server.shutdown()
        val e = failure { api.createRoom(dead, "A", "hi-IN") }
        assertTrue(e.isNetwork)
    }
}
