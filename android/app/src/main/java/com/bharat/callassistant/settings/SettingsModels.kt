package com.bharat.callassistant.settings

import com.bharat.callassistant.core.Languages
import com.bharat.callassistant.core.network.DEFAULT_SERVER_URL
import com.bharat.callassistant.core.protocol.TalkMode
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first

data class AppSettings(
    val serverUrl: String = DEFAULT_SERVER_URL,
    val mode: TalkMode = TalkMode.Auto,
    /** Multiplies all text sizes. 1.0 is the system size. */
    val fontScale: Float = 1.0f,
    val name: String = "",
    val language: String = Languages.DEFAULT,
)

const val MIN_FONT_SCALE = 0.9f
const val MAX_FONT_SCALE = 1.6f

interface SettingsStore {
    val settings: Flow<AppSettings>
    suspend fun update(transform: (AppSettings) -> AppSettings)
}

suspend fun SettingsStore.current(): AppSettings = settings.first()
