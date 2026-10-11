package com.bharat.callassistant.join

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.bharat.callassistant.R
import com.bharat.callassistant.call.CallService
import com.bharat.callassistant.core.Languages
import com.bharat.callassistant.ui.BigButton
import com.bharat.callassistant.ui.TouchTarget

@Composable
fun JoinScreen(
    onStartCall: () -> Unit,
    onOpenHistory: () -> Unit,
    onOpenSettings: () -> Unit,
    vm: JoinViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    var micDenied by remember { mutableStateOf(false) }

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { result ->
        if (result[Manifest.permission.RECORD_AUDIO] == true) {
            micDenied = false
            vm.submit()
        } else {
            micDenied = true
        }
    }

    fun submit() {
        val granted = ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED
        if (granted) {
            vm.submit()
        } else {
            val wanted = buildList {
                add(Manifest.permission.RECORD_AUDIO)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    add(Manifest.permission.POST_NOTIFICATIONS)
                }
            }
            permissionLauncher.launch(wanted.toTypedArray())
        }
    }

    LaunchedEffect(Unit) {
        vm.events.collect { event ->
            when (event) {
                JoinEvent.StartCall -> {
                    CallService.start(context)
                    onStartCall()
                }
            }
        }
    }

    Column(
        modifier = Modifier
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.End,
        ) {
            IconButton(onClick = onOpenHistory, modifier = Modifier.size(TouchTarget)) {
                Icon(Icons.Filled.History, contentDescription = stringResource(R.string.open_history))
            }
            IconButton(onClick = onOpenSettings, modifier = Modifier.size(TouchTarget)) {
                Icon(Icons.Filled.Settings, contentDescription = stringResource(R.string.open_settings))
            }
        }

        Text(stringResource(R.string.join_title), style = MaterialTheme.typography.headlineMedium)
        Text(stringResource(R.string.join_subtitle), style = MaterialTheme.typography.bodyLarge)

        OutlinedTextField(
            value = state.name,
            onValueChange = vm::setName,
            label = { Text(stringResource(R.string.your_name)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
            textStyle = MaterialTheme.typography.bodyLarge,
        )

        LanguagePicker(selected = state.language, onSelect = vm::setLanguage)

        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            FilterChip(
                selected = state.joinMode == JoinMode.NewRoom,
                onClick = { vm.setJoinMode(JoinMode.NewRoom) },
                label = { Text(stringResource(R.string.new_room), style = MaterialTheme.typography.labelLarge) },
                modifier = Modifier.height(TouchTarget),
            )
            FilterChip(
                selected = state.joinMode == JoinMode.JoinRoom,
                onClick = { vm.setJoinMode(JoinMode.JoinRoom) },
                label = { Text(stringResource(R.string.join_room), style = MaterialTheme.typography.labelLarge) },
                modifier = Modifier.height(TouchTarget),
            )
        }

        if (state.joinMode == JoinMode.JoinRoom) {
            OutlinedTextField(
                value = state.code,
                onValueChange = vm::setCode,
                label = { Text(stringResource(R.string.room_code)) },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                modifier = Modifier.fillMaxWidth(),
                textStyle = MaterialTheme.typography.headlineSmall,
            )
        }

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .toggleable(
                    value = state.consent,
                    role = Role.Checkbox,
                    onValueChange = vm::setConsent,
                )
                .padding(vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Checkbox(checked = state.consent, onCheckedChange = null, modifier = Modifier.size(TouchTarget))
            Text(
                stringResource(R.string.consent_text),
                style = MaterialTheme.typography.bodyLarge,
                modifier = Modifier.padding(start = 8.dp),
            )
        }

        val problem = when {
            micDenied -> stringResource(R.string.permission_needed)
            else -> state.error?.let { errorText(it, state.errorDetail) }
        }
        if (problem != null) {
            Text(
                problem,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodyLarge,
                modifier = Modifier.semantics { liveRegion = LiveRegionMode.Assertive },
            )
        }

        Button(
            onClick = ::submit,
            enabled = !state.loading,
            modifier = Modifier
                .fillMaxWidth()
                .height(BigButton),
        ) {
            if (state.loading) {
                CircularProgressIndicator(modifier = Modifier.size(28.dp), strokeWidth = 3.dp)
                Spacer(Modifier.size(12.dp))
                Text(stringResource(R.string.working), style = MaterialTheme.typography.titleMedium)
            } else {
                val label = if (state.joinMode == JoinMode.NewRoom) R.string.start_call else R.string.join_call
                Text(stringResource(label), style = MaterialTheme.typography.titleMedium)
            }
        }
    }
}

@Composable
private fun errorText(error: JoinError, detail: String?): String = when (error) {
    JoinError.NameEmpty -> stringResource(R.string.error_name_empty)
    JoinError.ConsentMissing -> stringResource(R.string.error_consent)
    JoinError.CodeInvalid -> stringResource(R.string.error_code)
    JoinError.Network -> stringResource(R.string.error_network)
    JoinError.Server -> stringResource(R.string.error_server, detail.orEmpty())
}

@Composable
private fun LanguagePicker(selected: String, onSelect: (String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Column {
        Text(stringResource(R.string.your_language), style = MaterialTheme.typography.bodyMedium)
        OutlinedButton(
            onClick = { open = true },
            modifier = Modifier
                .fillMaxWidth()
                .height(TouchTarget),
        ) {
            val lang = Languages.supported.firstOrNull { it.code == selected }
            Text(
                lang?.let { "${it.nativeName}  (${it.englishName})" } ?: selected,
                style = MaterialTheme.typography.bodyLarge,
            )
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            Languages.supported.forEach { lang ->
                DropdownMenuItem(
                    text = {
                        Text("${lang.nativeName}  (${lang.englishName})", style = MaterialTheme.typography.bodyLarge)
                    },
                    onClick = {
                        onSelect(lang.code)
                        open = false
                    },
                    modifier = Modifier.height(TouchTarget),
                )
            }
        }
    }
}
