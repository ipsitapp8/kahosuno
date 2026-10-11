package com.bharat.callassistant.call

import androidx.lifecycle.ViewModel
import com.bharat.callassistant.core.protocol.TalkMode
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.StateFlow
import javax.inject.Inject

@HiltViewModel
class CallViewModel @Inject constructor(
    private val controller: CallController,
) : ViewModel() {
    val state: StateFlow<CallUiState> = controller.state

    fun toggleMute() = controller.setMuted(!state.value.muted)
    fun toggleSpeaker() = controller.setSpeaker(!state.value.speakerOn)
    fun setMode(mode: TalkMode) = controller.setMode(mode)
    fun pttPressed(down: Boolean) = controller.pttPressed(down)
    fun dismissScam() = controller.dismissScam()
    fun hangUp() = controller.hangUp()
}
