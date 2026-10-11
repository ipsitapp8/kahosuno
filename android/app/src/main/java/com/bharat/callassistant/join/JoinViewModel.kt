package com.bharat.callassistant.join

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.bharat.callassistant.call.CallParams
import com.bharat.callassistant.call.CallStarter
import com.bharat.callassistant.core.Languages
import com.bharat.callassistant.core.network.ApiException
import com.bharat.callassistant.core.network.RoomApi
import com.bharat.callassistant.settings.SettingsStore
import com.bharat.callassistant.settings.current
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

enum class JoinMode { NewRoom, JoinRoom }

enum class JoinError { NameEmpty, ConsentMissing, CodeInvalid, Network, Server }

data class JoinUiState(
    val name: String = "",
    val language: String = Languages.DEFAULT,
    val joinMode: JoinMode = JoinMode.NewRoom,
    val code: String = "",
    val consent: Boolean = false,
    val loading: Boolean = false,
    val error: JoinError? = null,
    val errorDetail: String? = null,
)

sealed interface JoinEvent {
    /** The session is prepared: start the foreground service and open the call screen. */
    data object StartCall : JoinEvent
}

private val CODE_PATTERN = Regex("\\d{6}")

@HiltViewModel
class JoinViewModel @Inject constructor(
    private val api: RoomApi,
    private val settings: SettingsStore,
    private val starter: CallStarter,
) : ViewModel() {

    private val _state = MutableStateFlow(JoinUiState())
    val state: StateFlow<JoinUiState> = _state.asStateFlow()

    private val _events = Channel<JoinEvent>(Channel.BUFFERED)
    val events: Flow<JoinEvent> = _events.receiveAsFlow()

    init {
        // Pre-fill what the person used last time.
        viewModelScope.launch {
            val saved = settings.settings.first()
            _state.update {
                if (it.name.isEmpty()) it.copy(name = saved.name, language = saved.language) else it
            }
        }
    }

    fun setName(value: String) = _state.update { it.copy(name = value.take(40), error = null) }
    fun setLanguage(code: String) = _state.update { it.copy(language = code) }
    fun setJoinMode(mode: JoinMode) = _state.update { it.copy(joinMode = mode, error = null) }
    fun setConsent(value: Boolean) = _state.update { it.copy(consent = value, error = null) }
    fun setCode(value: String) =
        _state.update { it.copy(code = value.filter(Char::isDigit).take(6), error = null) }

    fun submit() {
        val s = _state.value
        if (s.loading) return
        val name = s.name.trim()
        val problem = when {
            name.isEmpty() -> JoinError.NameEmpty
            !s.consent -> JoinError.ConsentMissing
            s.joinMode == JoinMode.JoinRoom && !CODE_PATTERN.matches(s.code) -> JoinError.CodeInvalid
            else -> null
        }
        if (problem != null) {
            _state.update { it.copy(error = problem, errorDetail = null) }
            return
        }
        viewModelScope.launch {
            _state.update { it.copy(loading = true, error = null, errorDetail = null) }
            try {
                val app = settings.current()
                val ticket = when (s.joinMode) {
                    JoinMode.NewRoom -> api.createRoom(app.serverUrl, name, s.language)
                    JoinMode.JoinRoom -> api.joinRoom(app.serverUrl, s.code, name, s.language)
                }
                settings.update { it.copy(name = name, language = s.language) }
                starter.prepare(
                    CallParams(
                        serverUrl = app.serverUrl,
                        roomId = ticket.roomId,
                        code = ticket.code,
                        token = ticket.token,
                        name = name,
                        language = s.language,
                        mode = app.mode,
                    ),
                )
                _events.send(JoinEvent.StartCall)
            } catch (e: ApiException) {
                _state.update {
                    it.copy(
                        error = if (e.isNetwork) JoinError.Network else JoinError.Server,
                        errorDetail = e.message,
                    )
                }
            } finally {
                _state.update { it.copy(loading = false) }
            }
        }
    }
}
