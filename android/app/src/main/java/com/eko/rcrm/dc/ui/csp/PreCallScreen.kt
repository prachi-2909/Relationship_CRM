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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Call
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.eko.rcrm.dc.domain.model.PreCall
import com.eko.rcrm.dc.nativecall.rememberNativeCallLauncher
import com.eko.rcrm.dc.ui.common.AppCard
import com.eko.rcrm.dc.ui.common.AppTopBar
import com.eko.rcrm.dc.ui.common.BriefingActions
import com.eko.rcrm.dc.ui.common.BulletLine
import com.eko.rcrm.dc.ui.common.ErrorBanner
import com.eko.rcrm.dc.ui.common.LoadingIndicator
import com.eko.rcrm.dc.ui.common.MemoryCard
import com.eko.rcrm.dc.ui.common.OpenCommitmentRow
import com.eko.rcrm.dc.ui.common.PerformanceCard
import com.eko.rcrm.dc.ui.common.SectionCard
import com.eko.rcrm.dc.ui.common.StatusBadge
import com.eko.rcrm.dc.ui.common.SuggestedCommitmentRow
import com.eko.rcrm.dc.ui.common.SuggestionLine
import com.eko.rcrm.dc.ui.common.SuppressedNote
import com.eko.rcrm.dc.ui.common.Tone
import com.eko.rcrm.dc.ui.theme.Background
import com.eko.rcrm.dc.ui.theme.MutedForeground
import com.eko.rcrm.dc.ui.theme.Primary
import com.eko.rcrm.dc.ui.theme.Saffron

/** "Before you call": the RM's briefing on one CSP - talking points, what each side committed to, slab
 * status, the last call and relationship memory - with the call buttons right there. It reads the same
 * backend briefing as the web CRM. */
@Composable
fun PreCallScreen(
    onBack: () -> Unit,
    onCallStarted: (Int) -> Unit,
    viewModel: PreCallViewModel = hiltViewModel()
) {
    val state by viewModel.uiState.collectAsState()

    val launchNativeCall = rememberNativeCallLauncher(onPermissionDenied = {})
    LaunchedEffect(Unit) { viewModel.launchNativeCall.collect { request -> launchNativeCall(request) } }
    LaunchedEffect(Unit) { viewModel.navigateToReview.collect { id -> onCallStarted(id) } }

    // Coming back from a call (or the web CRM changing something) must not leave stale commitments up.
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) viewModel.refresh()
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    val actions = remember(state.busy) {
        BriefingActions(
            busy = state.busy,
            onStatus = viewModel::setStatus,
            onDuplicate = viewModel::reviewDuplicate,
            onRate = viewModel::rate
        )
    }

    Scaffold(
        containerColor = Background,
        topBar = { AppTopBar(title = "Before you call", onBack = onBack) }
    ) { padding ->
        Box(modifier = Modifier.fillMaxSize().padding(padding)) {
            val data = state.data
            when {
                state.isLoading && data == null -> LoadingIndicator()
                data == null -> ErrorBanner(
                    message = state.error ?: "Could not load the briefing.",
                    modifier = Modifier.padding(20.dp)
                )
                else -> PreCallContent(
                    data = data,
                    actions = actions,
                    actionError = state.actionError,
                    onCall = viewModel::call
                )
            }
        }
    }
}

@Composable
private fun PreCallContent(
    data: PreCall,
    actions: BriefingActions,
    actionError: String?,
    onCall: (String) -> Unit
) {
    LazyColumn(
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item { HeaderCard(data = data, onCall = onCall) }

        actionError?.let { message -> item { ErrorBanner(message = message) } }

        if (data.isEmpty) {
            item {
                Text(
                    text = "No earlier calls or open items for this CSP yet - the briefing fills in after " +
                        "your first recorded call.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MutedForeground
                )
            }
        }

        data.performance?.let { item { PerformanceCard(it) } }

        if (data.talkingPoints.isNotEmpty()) {
            item {
                SectionCard(title = "Talking points", accent = Saffron) {
                    data.talkingPoints.forEach { SuggestionLine(it, actions) }
                    SuppressedNote(data.suppressedCount)
                }
            }
        }

        if (data.suggested.isNotEmpty()) {
            item {
                SectionCard(
                    title = "Suggested from your calls",
                    subtitle = "Picked out of your call briefs by the AI. Accept what was really agreed; dismiss the rest."
                ) {
                    data.suggested.forEach { SuggestedCommitmentRow(it, actions, "You", "They") }
                }
            }
        }

        if (data.youCommitted.isNotEmpty()) {
            item {
                SectionCard(title = "You committed") {
                    data.youCommitted.forEach { OpenCommitmentRow(it, actions, "You", "They") }
                }
            }
        }

        if (data.theyCommitted.isNotEmpty()) {
            item {
                SectionCard(title = "They committed") {
                    data.theyCommitted.forEach { OpenCommitmentRow(it, actions, "You", "They") }
                }
            }
        }

        if (data.slabStatus.isNotEmpty()) {
            item {
                SectionCard(title = "Current slab status") {
                    data.slabStatus.forEach { BulletLine("•", it) }
                }
            }
        }

        data.lastCall?.let { last ->
            item {
                SectionCard(title = "Last call · ${last.whenIso.take(10)}") {
                    Text(
                        text = last.summary.ifBlank { "No summary." },
                        style = MaterialTheme.typography.bodyMedium
                    )
                }
            }
        }

        if (data.memory.isNotEmpty()) {
            item { MemoryCard(facts = data.memory) }
        }
    }
}

@Composable
private fun HeaderCard(data: PreCall, onCall: (String) -> Unit) {
    AppCard(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = data.name,
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f)
                )
                data.category?.takeIf { it.isNotBlank() }?.let { StatusBadge(text = it, tone = Tone.Neutral) }
            }
            val sub = listOfNotNull(data.cspId, data.branch).joinToString(" · ")
            if (sub.isNotBlank()) {
                Text(text = sub, style = MaterialTheme.typography.bodySmall, color = MutedForeground)
            }
            Text(
                text = if (data.callsCount == 0) "No calls yet" else
                    "${data.callsCount} earlier call${if (data.callsCount == 1) "" else "s"}",
                style = MaterialTheme.typography.bodySmall,
                color = MutedForeground,
                modifier = Modifier.padding(top = 2.dp)
            )
            data.mobile?.takeIf { it.isNotBlank() }?.let { DialRow("Primary", it, onCall) }
            data.alternateMobile?.takeIf { it.isNotBlank() && it != data.mobile }?.let {
                DialRow("Alternate", it, onCall)
            }
        }
    }
}

@Composable
private fun DialRow(label: String, number: String, onCall: (String) -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Column {
            Text(text = label, style = MaterialTheme.typography.labelSmall, color = MutedForeground)
            Text(text = number, style = MaterialTheme.typography.bodyMedium, color = Primary)
        }
        FilledIconButton(
            onClick = { onCall(number) },
            colors = IconButtonDefaults.filledIconButtonColors(containerColor = Primary, contentColor = Color.White)
        ) {
            Icon(Icons.Default.Call, contentDescription = "Call $number")
        }
    }
}
