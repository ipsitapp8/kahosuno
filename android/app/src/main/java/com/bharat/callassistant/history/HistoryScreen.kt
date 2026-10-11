package com.bharat.callassistant.history

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.bharat.callassistant.R
import com.bharat.callassistant.core.Languages
import com.bharat.callassistant.ui.AlertRed
import com.bharat.callassistant.ui.TouchTarget
import java.text.DateFormat
import java.util.Date

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HistoryScreen(onBack: () -> Unit, vm: HistoryViewModel = hiltViewModel()) {
    val entries by vm.entries.collectAsStateWithLifecycle()
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.history_title), style = MaterialTheme.typography.titleLarge) },
                navigationIcon = {
                    IconButton(onClick = onBack, modifier = Modifier.size(TouchTarget)) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = stringResource(R.string.back))
                    }
                },
            )
        },
    ) { padding ->
        Column(modifier = Modifier.padding(padding)) {
            Text(
                stringResource(R.string.history_note),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.outline,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
            )
            if (entries.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(stringResource(R.string.history_empty), style = MaterialTheme.typography.bodyLarge)
                }
            } else {
                LazyColumn(
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    items(entries, key = { it.id }) { HistoryCard(it) }
                }
            }
        }
    }
}

@Composable
private fun HistoryCard(entry: HistoryEntry) {
    val flagged = entry.maxScam != "none"
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(
                stringResource(
                    R.string.history_item_title,
                    entry.peerName.ifEmpty { "-" },
                    Languages.nativeName(entry.peerLanguage),
                ),
                style = MaterialTheme.typography.titleMedium,
            )
            Text(
                stringResource(
                    R.string.history_item_detail,
                    DateFormat.getDateTimeInstance(DateFormat.MEDIUM, DateFormat.SHORT).format(Date(entry.startedAt)),
                    "%d:%02d".format(entry.durationSec / 60, entry.durationSec % 60),
                    entry.avgLatencyMs,
                ),
                style = MaterialTheme.typography.bodyMedium,
            )
            Text(
                stringResource(
                    when (entry.maxScam) {
                        "high" -> R.string.history_scam_high
                        "suspicious" -> R.string.history_scam_suspicious
                        else -> R.string.history_scam_none
                    },
                ),
                style = MaterialTheme.typography.bodyMedium,
                color = if (flagged) AlertRed else MaterialTheme.colorScheme.outline,
            )
        }
    }
}
