package com.eko.rcrm.dc.ui.common

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.eko.rcrm.dc.domain.model.CallSession
import com.eko.rcrm.dc.ui.theme.MutedForeground
import com.eko.rcrm.dc.ui.theme.Surface

@Composable
fun CallSessionRow(call: CallSession, onClick: () -> Unit) {
    Card(
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = Surface),
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(
                    text = call.officialName ?: call.phoneRef ?: "Unknown caller",
                    style = MaterialTheme.typography.titleMedium
                )
                Text(
                    text = call.startedAt?.take(10) ?: "",
                    style = MaterialTheme.typography.bodySmall,
                    color = MutedForeground
                )
            }
            androidx.compose.foundation.layout.Spacer(modifier = Modifier.padding(top = 8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                StatusBadge(
                    text = call.processingStatus ?: "unknown",
                    tone = processingStatusTone(call.processingStatus)
                )
                StatusBadge(
                    text = call.identityStatus ?: "unidentified",
                    tone = identityStatusTone(call.identityStatus)
                )
            }
        }
    }
}
