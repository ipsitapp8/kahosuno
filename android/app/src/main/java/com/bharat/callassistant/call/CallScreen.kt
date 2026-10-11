package com.bharat.callassistant.call

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CallEnd
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.material.icons.filled.PhoneInTalk
import androidx.compose.material.icons.automirrored.filled.VolumeUp
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.bharat.callassistant.R
import com.bharat.callassistant.core.Languages
import com.bharat.callassistant.core.protocol.TalkMode
import com.bharat.callassistant.ui.AlertRed
import com.bharat.callassistant.ui.BigButton
import com.bharat.callassistant.ui.GoodGreen
import com.bharat.callassistant.ui.TouchTarget

@Composable
fun CallScreen(onFinished: () -> Unit, vm: CallViewModel = hiltViewModel()) {
    val state by vm.state.collectAsStateWithLifecycle()
    KeepScreenOn()
    BackHandler(enabled = state.isActive) { vm.hangUp() }

    when (state.phase) {
        Phase.Idle -> LaunchedEffect(Unit) { onFinished() } // opened without a call
        Phase.Ended -> EndedPane(state, onFinished)
        else -> ActivePane(state, vm)
    }
}

@Composable
private fun KeepScreenOn() {
    val view = LocalView.current
    DisposableEffect(view) {
        view.keepScreenOn = true
        onDispose { view.keepScreenOn = false }
    }
}

@Composable
private fun EndedPane(state: CallUiState, onFinished: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        val message = when (state.endReason) {
            EndReason.ConnectionLost -> stringResource(R.string.call_ended_connection)
            EndReason.ServerError, EndReason.AudioError ->
                stringResource(R.string.call_ended_error, state.endDetail.orEmpty())
            else -> stringResource(R.string.call_ended)
        }
        Text(
            message,
            style = MaterialTheme.typography.headlineSmall,
            textAlign = TextAlign.Center,
            modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
        )
        Button(
            onClick = onFinished,
            modifier = Modifier
                .padding(top = 32.dp)
                .fillMaxWidth()
                .height(BigButton),
        ) {
            Text(stringResource(R.string.back_to_home), style = MaterialTheme.typography.titleMedium)
        }
    }
}

@Composable
private fun ActivePane(state: CallUiState, vm: CallViewModel) {
    Column(modifier = Modifier.fillMaxSize()) {
        StatusHeader(state)

        val scam = state.scam
        if (scam != null && !scam.dismissed) {
            ScamBanner(scam = scam, onHangUp = vm::hangUp, onDismiss = vm::dismissScam)
        }

        if (state.phase == Phase.Waiting && state.roomCode.isNotEmpty()) {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(16.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer),
            ) {
                Text(
                    stringResource(R.string.share_code, state.roomCode),
                    style = MaterialTheme.typography.headlineSmall,
                    textAlign = TextAlign.Center,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(20.dp),
                )
            }
        }

        Transcript(state, modifier = Modifier.weight(1f))

        Controls(state, vm)
    }
}

@Composable
private fun StatusHeader(state: CallUiState) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        val status = when (state.phase) {
            Phase.Connecting -> stringResource(R.string.connecting)
            Phase.Reconnecting -> stringResource(R.string.reconnecting)
            Phase.Waiting -> stringResource(R.string.waiting_peer)
            else -> state.peer?.let {
                stringResource(R.string.in_call_with, it.name) + " (${Languages.nativeName(it.language)})"
            } ?: ""
        }
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                status,
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier
                    .weight(1f)
                    .semantics { liveRegion = LiveRegionMode.Polite },
            )
            Text(formatElapsed(state.elapsedSec), style = MaterialTheme.typography.titleMedium)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            state.tone?.let { tone ->
                AssistChip(onClick = {}, label = { Text(toneLabel(tone), style = MaterialTheme.typography.labelMedium) })
            }
            state.lastLatencyMs?.let { ms ->
                AssistChip(
                    onClick = {},
                    label = {
                        Text(
                            stringResource(R.string.latency_label) + ": " + stringResource(R.string.latency_value, ms),
                            style = MaterialTheme.typography.labelMedium,
                        )
                    },
                )
            }
        }
    }
}

@Composable
private fun toneLabel(tone: String): String = when (tone) {
    "excited" -> stringResource(R.string.tone_excited)
    "angry" -> stringResource(R.string.tone_angry)
    "sad" -> stringResource(R.string.tone_sad)
    else -> stringResource(R.string.tone_calm)
}

private fun formatElapsed(seconds: Int): String = "%d:%02d".format(seconds / 60, seconds % 60)

@Composable
private fun Transcript(state: CallUiState, modifier: Modifier = Modifier) {
    val listState = rememberLazyListState()
    LaunchedEffect(state.transcript.size) {
        if (state.transcript.isNotEmpty()) listState.animateScrollToItem(state.transcript.lastIndex)
    }
    if (state.transcript.isEmpty()) {
        Box(modifier = modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
            Text(
                stringResource(R.string.empty_transcript),
                style = MaterialTheme.typography.bodyLarge,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(24.dp),
            )
        }
    } else {
        LazyColumn(
            state = listState,
            modifier = modifier.fillMaxWidth(),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            items(state.transcript, key = { it.key }) { TranscriptBubble(it) }
        }
    }
}

@Composable
private fun Controls(state: CallUiState, vm: CallViewModel) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            FilledTonalButton(
                onClick = vm::toggleMute,
                modifier = Modifier
                    .weight(1f)
                    .height(TouchTarget),
            ) {
                Icon(
                    if (state.muted) Icons.Filled.MicOff else Icons.Filled.Mic,
                    contentDescription = null,
                )
                Text(
                    stringResource(if (state.muted) R.string.unmute else R.string.mute),
                    style = MaterialTheme.typography.labelLarge,
                    modifier = Modifier.padding(start = 8.dp),
                )
            }
            FilledTonalButton(
                onClick = vm::toggleSpeaker,
                modifier = Modifier
                    .weight(1f)
                    .height(TouchTarget),
            ) {
                Icon(
                    if (state.speakerOn) Icons.AutoMirrored.Filled.VolumeUp else Icons.Filled.PhoneInTalk,
                    contentDescription = null,
                )
                Text(
                    stringResource(if (state.speakerOn) R.string.speaker else R.string.earpiece),
                    style = MaterialTheme.typography.labelLarge,
                    modifier = Modifier.padding(start = 8.dp),
                )
            }
        }

        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            FilterChip(
                selected = state.mode == TalkMode.Auto,
                onClick = { vm.setMode(TalkMode.Auto) },
                label = { Text(stringResource(R.string.mode_auto), style = MaterialTheme.typography.labelLarge) },
                modifier = Modifier.height(TouchTarget),
            )
            FilterChip(
                selected = state.mode == TalkMode.PushToTalk,
                onClick = { vm.setMode(TalkMode.PushToTalk) },
                label = { Text(stringResource(R.string.mode_ptt), style = MaterialTheme.typography.labelLarge) },
                modifier = Modifier.height(TouchTarget),
            )
        }

        if (state.mode == TalkMode.PushToTalk) {
            HoldToTalkButton(held = state.pttHeld, onPress = vm::pttPressed)
        }

        Button(
            onClick = vm::hangUp,
            colors = ButtonDefaults.buttonColors(containerColor = AlertRed, contentColor = androidx.compose.ui.graphics.Color.White),
            modifier = Modifier
                .fillMaxWidth()
                .height(BigButton),
        ) {
            Icon(Icons.Filled.CallEnd, contentDescription = null)
            Text(
                stringResource(R.string.hang_up),
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(start = 8.dp),
            )
        }
    }
}

@Composable
private fun HoldToTalkButton(held: Boolean, onPress: (Boolean) -> Unit) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(BigButton + 12.dp)
            .clip(RoundedCornerShape(36.dp))
            .background(if (held) GoodGreen else MaterialTheme.colorScheme.primary)
            .pointerInput(Unit) {
                detectTapGestures(
                    onPress = {
                        onPress(true)
                        tryAwaitRelease()
                        onPress(false)
                    },
                )
            },
        contentAlignment = Alignment.Center,
    ) {
        Text(
            stringResource(R.string.hold_to_talk),
            color = androidx.compose.ui.graphics.Color.White,
            style = MaterialTheme.typography.titleLarge,
        )
    }
}
