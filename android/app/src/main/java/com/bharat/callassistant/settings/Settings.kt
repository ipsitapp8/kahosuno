package com.bharat.callassistant.settings

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.floatPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.bharat.callassistant.core.Languages
import com.bharat.callassistant.core.network.DEFAULT_SERVER_URL
import com.bharat.callassistant.core.protocol.TalkMode
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "settings")

@Singleton
class DataStoreSettings @Inject constructor(
    @ApplicationContext private val context: Context,
) : SettingsStore {
    private object Keys {
        val serverUrl = stringPreferencesKey("server_url")
        val mode = stringPreferencesKey("mode")
        val fontScale = floatPreferencesKey("font_scale")
        val name = stringPreferencesKey("name")
        val language = stringPreferencesKey("language")
    }

    private fun read(p: Preferences) = AppSettings(
        serverUrl = p[Keys.serverUrl] ?: DEFAULT_SERVER_URL,
        mode = TalkMode.fromWire(p[Keys.mode]),
        fontScale = (p[Keys.fontScale] ?: 1.0f).coerceIn(MIN_FONT_SCALE, MAX_FONT_SCALE),
        name = p[Keys.name].orEmpty(),
        language = p[Keys.language] ?: Languages.DEFAULT,
    )

    override val settings: Flow<AppSettings> = context.dataStore.data.map(::read)

    override suspend fun update(transform: (AppSettings) -> AppSettings) {
        context.dataStore.edit { p ->
            val new = transform(read(p))
            p[Keys.serverUrl] = new.serverUrl
            p[Keys.mode] = new.mode.wire
            p[Keys.fontScale] = new.fontScale.coerceIn(MIN_FONT_SCALE, MAX_FONT_SCALE)
            p[Keys.name] = new.name
            p[Keys.language] = new.language
        }
    }
}
