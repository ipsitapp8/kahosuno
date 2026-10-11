package com.bharat.callassistant.core.network

import java.net.URLEncoder

/** Emulator alias for the host machine's localhost. */
const val DEFAULT_SERVER_URL = "http://10.0.2.2:8000"

/**
 * Clean up what a person typed in Settings: trim, drop trailing slashes, and assume https for
 * anything that is not localhost or the emulator alias.
 */
fun normalizeBaseUrl(input: String): String {
    var url = input.trim().trimEnd('/')
    if (url.isEmpty()) return DEFAULT_SERVER_URL
    if (!url.contains("://")) {
        val host = url.substringBefore('/').substringBefore(':')
        val local = host == "localhost" || host == "10.0.2.2" || host == "127.0.0.1"
        url = (if (local) "http://" else "https://") + url
    }
    return url
}

/** http -> ws, https -> wss. */
fun webSocketUrl(baseUrl: String, roomId: String, token: String): String {
    val base = normalizeBaseUrl(baseUrl)
    val ws = when {
        base.startsWith("https://") -> "wss://" + base.removePrefix("https://")
        base.startsWith("http://") -> "ws://" + base.removePrefix("http://")
        else -> base
    }
    val encoded = URLEncoder.encode(token, "UTF-8")
    return "$ws/ws/v1/rooms/$roomId?token=$encoded"
}
