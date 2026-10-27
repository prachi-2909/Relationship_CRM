package com.eko.rcrm.dc.ui.calls

import androidx.compose.animation.Crossfade
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.compose.ui.platform.LocalLifecycleOwner
import com.eko.rcrm.dc.ui.common.AppTopBar
import com.eko.rcrm.dc.ui.common.CallSessionRow
import com.eko.rcrm.dc.ui.common.ErrorBanner
import com.eko.rcrm.dc.ui.common.LoadingIndicator
import com.eko.rcrm.dc.ui.history.CallHistoryViewModel
import com.eko.rcrm.dc.ui.pending.PendingQueueViewModel
import com.eko.rcrm.dc.ui.theme.Background
import com.eko.rcrm.dc.ui.theme.Muted
import com.eko.rcrm.dc.ui.theme.MutedForeground
import com.eko.rcrm.dc.ui.theme.OnBackground
import com.eko.rcrm.dc.ui.theme.Saffron
import com.eko.rcrm.dc.ui.theme.Surface

/** One screen for every call: "Pending" (awaiting review) and "History" (logged), as two tabs -
 * replaces the two separate Pending Queue / Call History screens. Reuses both existing view models. */
@Composable
fun CallsScreen(
    onBack: () -> Unit,
    onOpenCall: (Int) -> Unit,
    pendingViewModel: PendingQueueViewModel = hiltViewModel(),
    historyViewModel: CallHistoryViewModel = hiltViewModel()
) {
    val pending by pendingViewModel.uiState.collectAsState()
    val history by historyViewModel.uiState.collectAsState()
    var tab by remember { mutableIntStateOf(0) } // 0 = Pending, 1 = History

    // Both lists survive navigating away and back, so refresh them whenever this screen resumes.
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                pendingViewModel.refresh()
                historyViewModel.refresh()
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    Scaffold(
        containerColor = Background,
        topBar = { AppTopBar(title = "Calls", onBack = onBack) }
    ) { padding ->
        Column(modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 20.dp)) {
            Spacer(modifier = Modifier.height(12.dp))
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(Muted, RoundedCornerShape(14.dp))
                    .padding(4.dp),
                horizontalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                SegItem("Pending", selected = tab == 0, badge = pending.items.size,
                    onClick = { tab = 0 }, modifier = Modifier.weight(1f))
                SegItem("History", selected = tab == 1, badge = 0,
                    onClick = { tab = 1 }, modifier = Modifier.weight(1f))
            }
            Spacer(modifier = Modifier.height(14.dp))

            Crossfade(targetState = tab, label = "callsTab") { current ->
                // The two view models have distinct state types, so pull the shared fields out
                // per-branch (a plain `if/else` on the states themselves would widen to Any).
                val items = if (current == 0) pending.items else history.items
                val isLoading = if (current == 0) pending.isLoading else history.isLoading
                val error = if (current == 0) pending.error else history.error
                val emptyText = if (current == 0) "No calls awaiting review. Nice work."
                else "No calls logged yet."
                when {
                    isLoading && items.isEmpty() -> LoadingIndicator()
                    error != null && items.isEmpty() -> ErrorBanner(message = error)
                    items.isEmpty() -> Box(Modifier.fillMaxSize(), Alignment.Center) {
                        Text(
                            text = emptyText,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MutedForeground
                        )
                    }
                    else -> LazyColumn(
                        contentPadding = PaddingValues(bottom = 20.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        items(items, key = { it.id }) { call ->
                            CallSessionRow(call = call, onClick = { onOpenCall(call.id) })
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SegItem(
    label: String,
    selected: Boolean,
    badge: Int,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .background(if (selected) Surface else Color.Transparent, RoundedCornerShape(11.dp))
            .clickable(onClick = onClick)
            .padding(vertical = 9.dp),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelLarge,
            fontWeight = if (selected) FontWeight.Bold else FontWeight.Medium,
            color = if (selected) OnBackground else MutedForeground
        )
        if (badge > 0) {
            Spacer(modifier = Modifier.size(6.dp))
            Box(
                modifier = Modifier
                    .size(18.dp)
                    .background(Saffron, RoundedCornerShape(50)),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = if (badge > 99) "99+" else "$badge",
                    style = MaterialTheme.typography.labelSmall,
                    color = Color.White
                )
            }
        }
    }
}
