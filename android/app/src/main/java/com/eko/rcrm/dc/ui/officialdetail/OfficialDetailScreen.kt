package com.eko.rcrm.dc.ui.officialdetail

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.eko.rcrm.dc.domain.model.Official
import com.eko.rcrm.dc.domain.model.OfficialBriefing
import com.eko.rcrm.dc.nativecall.rememberNativeCallLauncher
import com.eko.rcrm.dc.ui.common.AppCard
import com.eko.rcrm.dc.ui.common.AppTopBar
import com.eko.rcrm.dc.ui.common.BriefingActions
import com.eko.rcrm.dc.ui.common.BulletLine
import com.eko.rcrm.dc.ui.common.CtaButton
import com.eko.rcrm.dc.ui.common.ErrorBanner
import com.eko.rcrm.dc.ui.common.LoadingIndicator
import com.eko.rcrm.dc.ui.common.MemoryCard
import com.eko.rcrm.dc.ui.common.OpenCommitmentRow
import com.eko.rcrm.dc.ui.common.SectionCard
import com.eko.rcrm.dc.ui.common.SuggestedCommitmentRow
import com.eko.rcrm.dc.ui.common.SuggestionLine
import com.eko.rcrm.dc.ui.common.SuppressedNote
import com.eko.rcrm.dc.ui.theme.Background
import com.eko.rcrm.dc.ui.theme.MutedForeground
import com.eko.rcrm.dc.ui.theme.Primary
import com.eko.rcrm.dc.ui.theme.Saffron

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

    // Coming back from a call must not leave a stale briefing up.
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) viewModel.refreshBriefing()
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    val actions = remember(uiState.busy) {
        BriefingActions(
            busy = uiState.busy,
            onStatus = viewModel::setStatus,
            onDuplicate = viewModel::reviewDuplicate,
            onRate = viewModel::rate
        )
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
                    .verticalScroll(rememberScrollState())
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

                Spacer(modifier = Modifier.height(20.dp))
                BriefingSection(
                    briefing = uiState.briefing,
                    error = uiState.briefingError,
                    actions = actions
                )
            }
        }
    }
}

/** The DC's relationship briefing: history, memory, who owes what, follow-ups and what to raise next. */
@Composable
private fun BriefingSection(briefing: OfficialBriefing?, error: String?, actions: BriefingActions) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        when {
            briefing == null -> Text(
                text = error ?: "Loading the relationship briefing…",
                style = MaterialTheme.typography.bodySmall,
                color = MutedForeground
            )
            briefing.isEmpty && briefing.relationshipLine == null -> Text(
                text = "No interactions or open items with this official yet - the briefing fills in as you " +
                    "log calls and follow-ups.",
                style = MaterialTheme.typography.bodyMedium,
                color = MutedForeground
            )
            else -> {
                briefing.relationshipLine?.let {
                    SectionCard(title = "Relationship") { Text(it, style = MaterialTheme.typography.bodyMedium) }
                }

                if (briefing.talkingPoints.isNotEmpty()) {
                    SectionCard(title = "Suggested discussion points", accent = Saffron) {
                        briefing.talkingPoints.forEach { SuggestionLine(it, actions) }
                        SuppressedNote(briefing.suppressedCount)
                    }
                }

                if (briefing.suggested.isNotEmpty()) {
                    SectionCard(
                        title = "Suggested from your calls",
                        subtitle = "Picked out of your call briefs by the AI. Accept what was really agreed; " +
                            "dismiss the rest."
                    ) {
                        briefing.suggested.forEach { SuggestedCommitmentRow(it, actions, "You", "Official") }
                    }
                }

                if (briefing.youCommitted.isNotEmpty()) {
                    SectionCard(title = "You committed") {
                        briefing.youCommitted.forEach { OpenCommitmentRow(it, actions, "You", "Official") }
                    }
                }

                if (briefing.theyCommitted.isNotEmpty()) {
                    SectionCard(title = "They committed") {
                        briefing.theyCommitted.forEach { OpenCommitmentRow(it, actions, "You", "Official") }
                    }
                }

                if (briefing.followups.isNotEmpty() || briefing.followupSuggestions.isNotEmpty()) {
                    SectionCard(title = "Follow-ups") {
                        briefing.followups.forEach {
                            BulletLine(
                                "•",
                                it.title + (it.dueAt?.let { d -> " (by $d${if (it.overdue) ", overdue" else ""})" } ?: "")
                            )
                        }
                        briefing.followupSuggestions.forEach { SuggestionLine(it, actions) }
                    }
                }

                if (briefing.upcoming.isNotEmpty()) {
                    SectionCard(title = "Coming up") { briefing.upcoming.forEach { BulletLine("•", it) } }
                }

                if (briefing.interactions.isNotEmpty()) {
                    SectionCard(title = "Recent interactions") {
                        briefing.interactions.forEach {
                            BulletLine("•", "${it.whenIso} · ${it.type.replace('_', ' ')} - ${it.summary}")
                        }
                    }
                }

                if (briefing.memory.isNotEmpty()) MemoryCard(facts = briefing.memory)
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
