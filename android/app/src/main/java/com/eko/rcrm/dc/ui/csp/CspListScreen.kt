package com.eko.rcrm.dc.ui.csp

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Call
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.eko.rcrm.dc.domain.model.Csp
import com.eko.rcrm.dc.nativecall.rememberNativeCallLauncher
import com.eko.rcrm.dc.ui.common.AppCard
import com.eko.rcrm.dc.ui.common.AppTopBar
import com.eko.rcrm.dc.ui.common.ErrorBanner
import com.eko.rcrm.dc.ui.common.LoadingIndicator
import com.eko.rcrm.dc.ui.theme.Background
import com.eko.rcrm.dc.ui.theme.MutedForeground
import com.eko.rcrm.dc.ui.theme.Primary

@Composable
fun CspListScreen(
    onBack: () -> Unit,
    onCallStarted: (Int) -> Unit,
    viewModel: CspListViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()

    // Place CSP calls through the app's own outbound flow (NativeCallForegroundService), which
    // reliably captures the number and records both sides - a plain ACTION_DIAL would often lose
    // the number on an outgoing call and record nothing.
    val launchNativeCall = rememberNativeCallLauncher(onPermissionDenied = {})
    LaunchedEffect(Unit) {
        viewModel.launchNativeCall.collect { request -> launchNativeCall(request) }
    }
    LaunchedEffect(Unit) {
        viewModel.navigateToReview.collect { callSessionId -> onCallStarted(callSessionId) }
    }

    Scaffold(
        containerColor = Background,
        topBar = { AppTopBar(title = "My CSPs", onBack = onBack) }
    ) { padding ->
        Box(modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 20.dp)) {
            when {
                uiState.isLoading && uiState.items.isEmpty() -> LoadingIndicator()
                uiState.error != null && uiState.items.isEmpty() -> ErrorBanner(message = uiState.error!!)
                uiState.items.isEmpty() -> Text(
                    text = "No CSPs assigned to you yet.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MutedForeground,
                    modifier = Modifier.align(Alignment.Center)
                )
                else -> LazyColumn(
                    contentPadding = PaddingValues(vertical = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    item {
                        Text(
                            text = "${uiState.items.size} CSP${if (uiState.items.size == 1) "" else "s"} assigned to you",
                            style = MaterialTheme.typography.bodySmall,
                            color = MutedForeground,
                            modifier = Modifier.padding(bottom = 4.dp)
                        )
                    }
                    items(uiState.items, key = { it.id }) { csp ->
                        CspRow(csp = csp, onDial = viewModel::call)
                    }
                }
            }
        }
    }
}

@Composable
private fun CspRow(csp: Csp, onDial: (String) -> Unit) {
    AppCard(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
            Text(text = csp.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            val sub = listOfNotNull(csp.category, csp.branchName, csp.district).joinToString(" · ")
            if (sub.isNotBlank()) {
                Text(text = sub, style = MaterialTheme.typography.bodySmall, color = MutedForeground)
            }
            csp.mobile?.takeIf { it.isNotBlank() }?.let { number ->
                NumberRow(label = "Call", number = number, onDial = onDial)
            }
            csp.alternateMobile?.takeIf { it.isNotBlank() && it != csp.mobile }?.let { number ->
                NumberRow(label = "Alt", number = number, onDial = onDial)
            }
            if (csp.mobile.isNullOrBlank() && csp.alternateMobile.isNullOrBlank()) {
                Text(
                    text = "No number on record",
                    style = MaterialTheme.typography.bodySmall,
                    color = MutedForeground,
                    modifier = Modifier.padding(top = 6.dp)
                )
            }
        }
    }
}

@Composable
private fun NumberRow(label: String, number: String, onDial: (String) -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Column {
            Text(text = label, style = MaterialTheme.typography.labelSmall, color = MutedForeground)
            Text(text = number, style = MaterialTheme.typography.bodyMedium, color = Primary)
        }
        androidx.compose.material3.FilledTonalIconButton(onClick = { onDial(number) }) {
            Icon(Icons.Default.Call, contentDescription = "Call $number", tint = Primary)
        }
    }
}
