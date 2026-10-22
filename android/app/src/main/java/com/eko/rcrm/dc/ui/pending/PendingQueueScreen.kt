package com.eko.rcrm.dc.ui.pending

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.eko.rcrm.dc.ui.common.AppTopBar
import com.eko.rcrm.dc.ui.common.CallSessionRow
import com.eko.rcrm.dc.ui.common.ErrorBanner
import com.eko.rcrm.dc.ui.common.LoadingIndicator
import com.eko.rcrm.dc.ui.theme.Background
import com.eko.rcrm.dc.ui.theme.MutedForeground

@Composable
fun PendingQueueScreen(
    onBack: () -> Unit,
    onOpenCall: (Int) -> Unit,
    viewModel: PendingQueueViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()

    // The ViewModel (and its initial load) survives navigating away and back via the
    // Compose back stack, so a freshly-started call wouldn't otherwise show up here
    // until the queue is reopened from scratch - refresh every time this screen
    // becomes visible again, not just on first creation.
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) viewModel.refresh()
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    Scaffold(
        containerColor = Background,
        topBar = { AppTopBar(title = "Pending Queue", onBack = onBack) }
    ) { padding ->
        Box(modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 20.dp)) {
            when {
                uiState.isLoading && uiState.items.isEmpty() -> LoadingIndicator()
                uiState.error != null && uiState.items.isEmpty() -> ErrorBanner(message = uiState.error!!)
                uiState.items.isEmpty() -> Text(
                    text = "No calls awaiting review. Nice work.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MutedForeground,
                    modifier = Modifier.align(Alignment.Center)
                )
                else -> LazyColumn(
                    contentPadding = PaddingValues(vertical = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    items(uiState.items, key = { it.id }) { call ->
                        CallSessionRow(call = call, onClick = { onOpenCall(call.id) })
                    }
                }
            }
        }
    }
}
