package com.bharat.callassistant.core.network

import com.bharat.callassistant.core.protocol.Protocol
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

data class RoomTicket(val roomId: String, val code: String, val token: String)

/** A problem reported by the server (or "network" when it could not be reached). */
class ApiException(val code: String, message: String) : Exception(message) {
    val isNetwork: Boolean get() = code == NETWORK

    companion object {
        const val NETWORK = "network"
    }
}

interface RoomApi {
    suspend fun createRoom(baseUrl: String, name: String, language: String): RoomTicket
    suspend fun joinRoom(baseUrl: String, code: String, name: String, language: String): RoomTicket
}

@Singleton
class HttpRoomApi @Inject constructor(base: OkHttpClient) : RoomApi {
    // A free-tier host can take about a minute to wake up on the first request.
    private val client = base.newBuilder().callTimeout(75, TimeUnit.SECONDS).build()

    override suspend fun createRoom(baseUrl: String, name: String, language: String) =
        post("${normalizeBaseUrl(baseUrl)}/rooms", name, language)

    override suspend fun joinRoom(baseUrl: String, code: String, name: String, language: String) =
        post("${normalizeBaseUrl(baseUrl)}/rooms/$code/join", name, language)

    private suspend fun post(url: String, name: String, language: String): RoomTicket =
        withContext(Dispatchers.IO) {
            val body = buildJsonObject {
                put("name", name)
                put("language", language)
                put("consent", true)
            }.toString().toRequestBody("application/json".toMediaType())
            val request = try {
                Request.Builder().url(url).post(body).build()
            } catch (e: IllegalArgumentException) { // an address typed in Settings that is not a URL
                throw ApiException(ApiException.NETWORK, "Invalid server address")
            }
            try {
                client.newCall(request).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    if (!resp.isSuccessful) throw parseError(resp.code, text)
                    val obj = Protocol.json.parseToJsonElement(text).jsonObject
                    RoomTicket(
                        roomId = obj.string("room_id"),
                        code = obj.string("code"),
                        token = obj.string("token"),
                    )
                }
            } catch (e: ApiException) {
                throw e
            } catch (e: IOException) {
                throw ApiException(ApiException.NETWORK, e.message ?: "network error")
            } catch (e: IllegalArgumentException) { // includes SerializationException
                throw ApiException("bad_response", "unreadable reply from server")
            }
        }

    private fun JsonObject.string(key: String): String =
        (this[key] as? JsonPrimitive)?.contentOrNull
            ?: throw ApiException("bad_response", "missing $key in server reply")

    /** FastAPI errors look like {"detail": {"code": "...", "message": "..."}} or a list. */
    private fun parseError(status: Int, text: String): ApiException {
        val detail = try {
            Protocol.json.parseToJsonElement(text).jsonObject["detail"]
        } catch (e: Exception) {
            null
        }
        return when (detail) {
            is JsonObject -> ApiException(
                (detail["code"] as? JsonPrimitive)?.contentOrNull ?: "http_$status",
                (detail["message"] as? JsonPrimitive)?.contentOrNull ?: "HTTP $status",
            )
            is JsonArray -> ApiException("bad_request", "Invalid input")
            else -> ApiException("http_$status", "HTTP $status")
        }
    }
}
