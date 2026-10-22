package com.eko.rcrm.dc.ui.officialdetail

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
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.eko.rcrm.dc.domain.model.Official
import com.eko.rcrm.dc.nativecall.rememberNativeCallLauncher
import com.eko.rcrm.dc.ui.common.AppCard
import com.eko.rcrm.dc.ui.common.AppTopBar
import com.eko.rcrm.dc.ui.common.CtaButton
import com.eko.rcrm.dc.ui.common.ErrorBanner
import com.eko.rcrm.dc.ui.common.LoadingIndicator
import com.eko.rcrm.dc.ui.theme.Background
import com.eko.rcrm.dc.ui.theme.MutedForeground
import com.eko.rcrm.dc.ui.theme.Primary

@Composable
fun OfficialDetailScreen(
    onBack: () -> Unit,
    onCallStarted: (Int) -> Unit,
    onEdit: (Int) -> Unit,
    viewModel: OfficialDetailViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    var permissionError by remember { mutableStateOf<String?>(null) }
    val launchNativeCall = rememberNativeCallLauncher(
        onPermissionDenied = { permissionError = "Call and phone-state permissions are needed to place this call." }
    )

    LaunchedEffect(Unit) {
        viewModel.launchNativeCall.collect { request -> launchNativeCall(request) }
    }

    LaunchedEffect(Unit) {
        viewModel.navigateToReview.collect { callSessionId -> onCallStarted(callSessionId) }
    }

    Scaffold(
        containerColor = Background,
        topBar = { AppTopBar(title = "Official", onBack = onBack) }
    ) { padding ->
        val official = uiState.official
        when {
            uiState.isLoading && official == null -> LoadingIndicator(modifier = Modifier.padding(padding))
            official == null -> ErrorBanner(
                message = uiState.error ?: "Could not load this official.",
                modifier = Modifier.padding(padding).padding(20.dp)
            )
            else -> Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .padding(20.dp)
            ) {
                DetailCard(official)

                (uiState.error ?: permissionError)?.let {
                    Spacer(modifier = Modifier.height(12.dp))
                    ErrorBanner(message = it)
                }

                Spacer(modifier = Modifier.height(20.dp))

                if (uiState.isStartingCall) {
                    CircularProgressIndicator(color = Primary)
                } else {
                    // Starts the call via POST /calls/outgoing; the response's channel
                    // decides whether that's Knowlarity (handled server-side) or this
                    // device's own SIM (launchNativeCall hands off to the native dialer).
                    CtaButton(
                        text = "Call",
                        onClick = viewModel::callOfficial,
                        enabled = official.phone != null,
                        modifier = Modifier.fillMaxWidth()
                    )
                }

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedButton(
                    onClick = { onEdit(official.id) },
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(14.dp)
                ) {
                    Icon(Icons.Default.Edit, contentDescription = null, tint = Primary)
                    Spacer(modifier = Modifier.padding(start = 4.dp))
                    Text("Edit official")
                }
            }
        }
    }
}

@Composable
private fun DetailCard(official: Official) {
    AppCard(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(text = official.name, style = MaterialTheme.typography.titleLarge)
            val subtitle = listOfNotNull(official.designation, official.department, official.location)
                .joinToString(" • ")
            if (subtitle.isNotBlank()) {
                Text(text = subtitle, style = MaterialTheme.typography.bodyMedium, color = MutedForeground)
            }
            Spacer(modifier = Modifier.height(8.dp))
            official.phone?.let {
                Text(text = "Phone: $it", style = MaterialTheme.typography.bodyMedium)
            }
            official.email?.let {
                Text(text = "Email: $it", style = MaterialTheme.typography.bodyMedium)
            }
            official.organizationUnitName?.let {
                Spacer(modifier = Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(
                        text = "$it (${official.organizationUnitType ?: "unit"})",
                        style = MaterialTheme.typography.bodySmall,
                        color = MutedForeground
                    )
                }
            }
        }
    }
}
