package com.bharat.callassistant.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.bharat.callassistant.core.protocol.TalkMode
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val store: SettingsStore,
) : ViewModel() {
    val settings: StateFlow<AppSettings> = store.settings
        .stateIn(viewModelScope, SharingStarted.Eagerly, AppSettings())

    fun setServerUrl(url: String) = save { it.copy(serverUrl = url.trim()) }
    fun setMode(mode: TalkMode) = save { it.copy(mode = mode) }
    fun setFontScale(scale: Float) =
        save { it.copy(fontScale = scale.coerceIn(MIN_FONT_SCALE, MAX_FONT_SCALE)) }

    private fun save(transform: (AppSettings) -> AppSettings) {
        viewModelScope.launch { store.update(transform) }
    }
}
