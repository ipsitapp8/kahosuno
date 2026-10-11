package com.bharat.callassistant.core.network

import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import okio.ByteString.Companion.toByteString
import javax.inject.Inject
import javax.inject.Singleton

sealed interface TransportEvent {
    data object Opened : TransportEvent
    data class Text(val text: String) : TransportEvent
    class Binary(val bytes: ByteArray) : TransportEvent
    data class Closed(val code: Int, val reason: String) : TransportEvent
    data class Failed(val error: Throwable) : TransportEvent
}

interface Connection {
    fun sendText(text: String): Boolean
    fun sendBinary(bytes: ByteArray): Boolean
    fun close()
}

/** A WebSocket-like pipe. Events arrive on a background thread. */
interface Transport {
    fun open(url: String, onEvent: (TransportEvent) -> Unit): Connection
}

@Singleton
class OkHttpTransport @Inject constructor(private val client: OkHttpClient) : Transport {
    override fun open(url: String, onEvent: (TransportEvent) -> Unit): Connection {
        val socket = client.newWebSocket(
            Request.Builder().url(url).build(),
            object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) =
                    onEvent(TransportEvent.Opened)

                override fun onMessage(webSocket: WebSocket, text: String) =
                    onEvent(TransportEvent.Text(text))

                override fun onMessage(webSocket: WebSocket, bytes: ByteString) =
                    onEvent(TransportEvent.Binary(bytes.toByteArray()))

                override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                    webSocket.close(code, null)
                    onEvent(TransportEvent.Closed(code, reason))
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) =
                    onEvent(TransportEvent.Closed(code, reason))

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) =
                    onEvent(TransportEvent.Failed(t))
            },
        )
        return object : Connection {
            override fun sendText(text: String) = socket.send(text)
            override fun sendBinary(bytes: ByteArray) = socket.send(bytes.toByteString())
            override fun close() {
                socket.close(1000, null)
            }
        }
    }
}
