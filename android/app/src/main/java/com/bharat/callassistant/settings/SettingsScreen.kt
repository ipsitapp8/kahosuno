package com.bharat.callassistant.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.bharat.callassistant.R
import com.bharat.callassistant.core.protocol.TalkMode
import com.bharat.callassistant.ui.TouchTarget

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(onBack: () -> Unit, vm: SettingsViewModel = hiltViewModel()) {
    val settings by vm.settings.collectAsStateWithLifecycle()

    // Keep what is being typed locally: writing to disk on every key and reading it straight
    // back would move the cursor.
    var serverUrl by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(settings.serverUrl) {
        if (serverUrl == null) serverUrl = settings.serverUrl
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.settings_title), style = MaterialTheme.typography.titleLarge) },
                navigationIcon = {
                    IconButton(onClick = onBack, modifier = Modifier.size(TouchTarget)) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = stringResource(R.string.back))
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            OutlinedTextField(
                value = serverUrl ?: settings.serverUrl,
                onValueChange = {
                    serverUrl = it
                    vm.setServerUrl(it)
                },
                label = { Text(stringResource(R.string.server_url)) },
                supportingText = { Text(stringResource(R.string.server_url_hint)) },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                textStyle = MaterialTheme.typography.bodyLarge,
                modifier = Modifier.fillMaxWidth(),
            )

            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(stringResource(R.string.default_mode), style = MaterialTheme.typography.titleMedium)
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    FilterChip(
                        selected = settings.mode == TalkMode.Auto,
                        onClick = { vm.setMode(TalkMode.Auto) },
                        label = { Text(stringResource(R.string.mode_auto), style = MaterialTheme.typography.labelLarge) },
                        modifier = Modifier.height(TouchTarget),
                    )
                    FilterChip(
                        selected = settings.mode == TalkMode.PushToTalk,
                        onClick = { vm.setMode(TalkMode.PushToTalk) },
                        label = { Text(stringResource(R.string.mode_ptt), style = MaterialTheme.typography.labelLarge) },
                        modifier = Modifier.height(TouchTarget),
                    )
                }
            }

            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                val fontLabel = stringResource(R.string.font_size)
                Text(fontLabel, style = MaterialTheme.typography.titleMedium)
                Slider(
                    value = settings.fontScale,
                    onValueChange = vm::setFontScale,
                    valueRange = MIN_FONT_SCALE..MAX_FONT_SCALE,
                    modifier = Modifier
                        .height(TouchTarget)
                        .semantics { contentDescription = fontLabel },
                )
                Text(stringResource(R.string.font_size_sample), style = MaterialTheme.typography.bodyLarge)
            }
        }
    }
}
