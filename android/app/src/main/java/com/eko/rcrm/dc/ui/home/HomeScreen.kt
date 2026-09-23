package com.eko.rcrm.dc.ui.home

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Logout
import androidx.compose.material.icons.filled.PendingActions
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.eko.rcrm.dc.ui.common.CtaButton
import com.eko.rcrm.dc.ui.theme.Accent
import com.eko.rcrm.dc.ui.theme.Background
import com.eko.rcrm.dc.ui.theme.MutedForeground
import com.eko.rcrm.dc.ui.theme.Primary
import com.eko.rcrm.dc.ui.theme.Surface

@Composable
fun HomeScreen(
    onSearchOfficials: () -> Unit,
    onPendingQueue: () -> Unit,
    onCallHistory: () -> Unit,
    onLoggedOut: () -> Unit,
    viewModel: HomeViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()

    LaunchedEffect(uiState.loggedOut) {
        if (uiState.loggedOut) onLoggedOut()
    }

    Scaffold(containerColor = Background) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(20.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column {
                    Text(text = "Welcome back", style = MaterialTheme.typography.bodyMedium, color = MutedForeground)
                    Text(
                        text = uiState.userName ?: "Field DC",
                        style = MaterialTheme.typography.headlineSmall
                    )
                }
                IconButton(onClick = viewModel::logout) {
                    Icon(Icons.Default.Logout, contentDescription = "Log out", tint = MutedForeground)
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            Card(
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = Surface),
                modifier = Modifier.fillMaxWidth()
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(20.dp),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Column {
                        Text(text = "Calls awaiting review", style = MaterialTheme.typography.bodyMedium, color = MutedForeground)
                        Text(
                            text = "${uiState.pendingCount}",
                            style = MaterialTheme.typography.headlineMedium,
                            color = if (uiState.pendingCount > 0) Primary else Accent
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(28.dp))

            CtaButton(
                text = "Call an Official",
                onClick = onSearchOfficials,
                modifier = Modifier.fillMaxWidth()
            )

            Spacer(modifier = Modifier.height(12.dp))

            OutlinedNavRow(
                icon = Icons.Default.PendingActions,
                label = "Pending Queue",
                trailingCount = uiState.pendingCount,
                onClick = onPendingQueue
            )

            Spacer(modifier = Modifier.height(12.dp))

            OutlinedNavRow(
                icon = Icons.Default.History,
                label = "Call History",
                trailingCount = null,
                onClick = onCallHistory
            )

            Spacer(modifier = Modifier.height(12.dp))

            OutlinedNavRow(
                icon = Icons.Default.Search,
                label = "Search Officials",
                trailingCount = null,
                onClick = onSearchOfficials
            )
        }
    }
}

@Composable
private fun OutlinedNavRow(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    label: String,
    trailingCount: Int?,
    onClick: () -> Unit
) {
    Card(
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = Surface),
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Row {
                Icon(icon, contentDescription = null, tint = Primary)
                Text(
                    text = label,
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.padding(start = 12.dp)
                )
            }
            if (trailingCount != null && trailingCount > 0) {
                Text(text = "$trailingCount", style = MaterialTheme.typography.titleMedium, color = Primary)
            }
        }
    }
}
