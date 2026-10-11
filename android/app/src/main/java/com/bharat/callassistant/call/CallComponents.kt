package com.bharat.callassistant.call

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bharat.callassistant.R
import com.bharat.callassistant.core.protocol.ScamLevel
import com.bharat.callassistant.core.protocol.Speaker
import com.bharat.callassistant.ui.AlertRed
import com.bharat.callassistant.ui.AlertYellow
import com.bharat.callassistant.ui.BigButton

/**
 * Full-width warning. Yellow = suspicious, red = high. Announced to screen readers at once.
 * "Call kaato" hangs up with one tap.
 */
@Composable
fun ScamBanner(scam: ScamState, onHangUp: () -> Unit, onDismiss: () -> Unit) {
    val high = scam.level == ScamLevel.High
    val background = if (high) AlertRed else AlertYellow
    val foreground = if (high) Color.White else Color.Black
    Surface(
        color = background,
        contentColor = foreground,
        modifier = Modifier
            .fillMaxWidth()
            .semantics { liveRegion = LiveRegionMode.Assertive },
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.Warning, contentDescription = null, modifier = Modifier.padding(end = 10.dp))
                Text(
                    stringResource(if (high) R.string.scam_high_title else R.string.scam_suspicious_title),
                    style = MaterialTheme.typography.titleMedium,
                )
            }
            scam.reasons.forEach { reason ->
                Text("• $reason", style = MaterialTheme.typography.bodyLarge)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                Button(
                    onClick = onHangUp,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = foreground,
                        contentColor = background,
                    ),
                    modifier = Modifier
                        .weight(1f)
                        .height(BigButton),
                ) {
                    Text(stringResource(R.string.call_kaato), style = MaterialTheme.typography.labelLarge)
                }
                OutlinedButton(
                    onClick = onDismiss,
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = foreground),
                    modifier = Modifier
                        .weight(1f)
                        .height(BigButton),
                ) {
                    Text(stringResource(R.string.dismiss), style = MaterialTheme.typography.labelLarge)
                }
            }
        }
    }
}

/**
 * One line of the conversation. What the *listener* can read is shown large: for the other
 * person that is the translation, for yourself it is what you said. The other version is
 * shown small underneath.
 */
@Composable
fun TranscriptBubble(item: TranscriptItem) {
    val mine = item.speaker == Speaker.Self
    val large = if (mine) item.original else item.translated
    val small = if (mine) item.translated else item.original
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (mine) Arrangement.End else Arrangement.Start,
    ) {
        Surface(
            shape = RoundedCornerShape(18.dp),
            color = if (mine) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant,
            modifier = Modifier.widthIn(max = 320.dp),
        ) {
            Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                if (!mine) {
                    Text(
                        stringResource(R.string.they_said_label),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.outline,
                    )
                }
                Text(large, fontSize = 22.sp, lineHeight = 30.sp, color = MaterialTheme.colorScheme.onSurface)
                Text(
                    small,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.outline,
                )
                item.latencyMs?.let {
                    Text(
                        stringResource(R.string.latency_value, it),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.outline,
                    )
                }
            }
        }
    }
}
