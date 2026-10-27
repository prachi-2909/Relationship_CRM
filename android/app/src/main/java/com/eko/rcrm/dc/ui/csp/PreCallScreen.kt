package com.eko.rcrm.dc.ui.csp

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
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
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.eko.rcrm.dc.domain.model.Commitment
import com.eko.rcrm.dc.domain.model.PreCall
import com.eko.rcrm.dc.nativecall.rememberNativeCallLauncher
import com.eko.rcrm.dc.ui.common.AppCard
import com.eko.rcrm.dc.ui.common.AppTopBar
import com.eko.rcrm.dc.ui.common.ErrorBanner
import com.eko.rcrm.dc.ui.common.LoadingIndicator
import com.eko.rcrm.dc.ui.common.StatusBadge
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
                    busy = state.busy,
                    actionError = state.actionError,
                    onCall = viewModel::call,
                    onStatus = viewModel::setStatus
                )
            }
        }
    }
}

@Composable
private fun PreCallContent(
    data: PreCall,
    busy: Boolean,
    actionError: String?,
    onCall: (String) -> Unit,
    onStatus: (Int, String) -> Unit
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

        if (data.talkingPoints.isNotEmpty()) {
            item {
                SectionCard(title = "Talking points", accent = Saffron) {
                    data.talkingPoints.forEach { BulletLine("→", it) }
                }
            }
        }

        if (data.suggested.isNotEmpty()) {
            item {
                SectionCard(
                    title = "Suggested from your calls",
                    subtitle = "Picked out of your call briefs by the AI. Accept what was really agreed; dismiss the rest."
                ) {
                    data.suggested.forEach { c ->
                        CommitmentRow(c) {
                            TextButton(onClick = { onStatus(c.id, "open") }, enabled = !busy) { Text("Accept") }
                            TextButton(onClick = { onStatus(c.id, "cancelled") }, enabled = !busy) { Text("Dismiss") }
                        }
                    }
                }
            }
        }

        if (data.youCommitted.isNotEmpty()) {
            item {
                SectionCard(title = "You committed") {
                    data.youCommitted.forEach { c ->
                        CommitmentRow(c) {
                            TextButton(onClick = { onStatus(c.id, "done") }, enabled = !busy) { Text("Mark done") }
                        }
                    }
                }
            }
        }

        if (data.theyCommitted.isNotEmpty()) {
            item {
                SectionCard(title = "They committed") {
                    data.theyCommitted.forEach { c ->
                        CommitmentRow(c) {
                            TextButton(onClick = { onStatus(c.id, "done") }, enabled = !busy) { Text("Mark done") }
                        }
                    }
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

@Composable
private fun SectionCard(
    title: String,
    subtitle: String? = null,
    accent: Color? = null,
    content: @Composable ColumnScope.() -> Unit
) {
    AppCard(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
            Text(
                text = title.uppercase(),
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.SemiBold,
                color = accent ?: MutedForeground
            )
            subtitle?.let {
                Text(
                    text = it,
                    style = MaterialTheme.typography.bodySmall,
                    color = MutedForeground,
                    modifier = Modifier.padding(top = 2.dp)
                )
            }
            Spacer(modifier = Modifier.height(8.dp))
            content()
        }
    }
}

@Composable
private fun BulletLine(bullet: String, text: String) {
    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
        Text(text = bullet, style = MaterialTheme.typography.bodyMedium, color = MutedForeground)
        Text(
            text = text,
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(start = 8.dp)
        )
    }
}

@Composable
private fun CommitmentRow(c: Commitment, actions: @Composable RowScope.() -> Unit) {
    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Text(text = c.text, style = MaterialTheme.typography.bodyMedium)
        Row(verticalAlignment = Alignment.CenterVertically) {
            StatusBadge(
                text = when (c.party) {
                    "ours" -> "You"
                    "theirs" -> "They"
                    else -> "Both"
                },
                tone = Tone.Neutral
            )
            c.dueDate?.let {
                Text(
                    text = "  by $it",
                    style = MaterialTheme.typography.bodySmall,
                    color = MutedForeground
                )
            }
            Spacer(modifier = Modifier.weight(1f))
            actions()
        }
    }
}

@Composable
private fun MemoryCard(facts: List<String>) {
    var expanded by remember { mutableStateOf(false) }
    AppCard(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.fillMaxWidth().padding(16.dp).animateContentSize()) {
            TextButton(onClick = { expanded = !expanded }) {
                Text(if (expanded) "Hide relationship memory" else "Show relationship memory (${facts.size})")
            }
            if (expanded) {
                facts.forEach { BulletLine("•", it) }
            }
        }
    }
}
