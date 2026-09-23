package com.eko.rcrm.dc.ui.review

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
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
import com.eko.rcrm.dc.domain.model.CallSession
import com.eko.rcrm.dc.domain.model.Official
import com.eko.rcrm.dc.ui.common.AppTopBar
import com.eko.rcrm.dc.ui.common.CtaButton
import com.eko.rcrm.dc.ui.common.ErrorBanner
import com.eko.rcrm.dc.ui.common.LoadingIndicator
import com.eko.rcrm.dc.ui.common.StatusBadge
import com.eko.rcrm.dc.ui.common.identityStatusTone
import com.eko.rcrm.dc.ui.common.processingStatusTone
import com.eko.rcrm.dc.ui.theme.Background
import com.eko.rcrm.dc.ui.theme.Destructive
import com.eko.rcrm.dc.ui.theme.MutedForeground
import com.eko.rcrm.dc.ui.theme.Primary
import com.eko.rcrm.dc.ui.theme.Surface

@Composable
fun CallReviewScreen(
    onBack: () -> Unit,
    onRecordVoiceNote: (Int) -> Unit,
    onManualTextEntry: (Int) -> Unit,
    onDone: () -> Unit,
    viewModel: CallReviewViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()

    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) viewModel.loadCall()
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    LaunchedEffect(uiState.confirmed, uiState.remindedLater) {
        if (uiState.confirmed || uiState.remindedLater) onDone()
    }

    val call = uiState.call

    Scaffold(
        containerColor = Background,
        topBar = { AppTopBar(title = "Call Review", onBack = onBack) }
    ) { padding ->
        when {
            uiState.isLoading && call == null -> LoadingIndicator(modifier = Modifier.padding(padding))
            call == null -> ErrorBanner(
                message = uiState.error ?: "Could not load this call.",
                modifier = Modifier.padding(padding).padding(20.dp)
            )
            else -> Column(
                modifier = Modifier
                    .padding(padding)
                    .verticalScroll(rememberScrollState())
                    .padding(20.dp)
            ) {
                CallMetadataCard(call)

                uiState.error?.let {
                    Spacer(modifier = Modifier.height(12.dp))
                    ErrorBanner(message = it)
                }

                Spacer(modifier = Modifier.height(16.dp))
                Text(text = "Transcript", style = MaterialTheme.typography.titleMedium)
                Spacer(modifier = Modifier.height(6.dp))
                TranscriptCard(call)

                Spacer(modifier = Modifier.height(16.dp))
                Text(
                    text = "Recording fail is never an interaction fail",
                    style = MaterialTheme.typography.titleMedium
                )
                Text(
                    text = "You can always add a voice recap or type notes below, whether or not a recording exists.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MutedForeground
                )
                Spacer(modifier = Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedButton(
                        onClick = { onRecordVoiceNote(call.id) },
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(14.dp)
                    ) {
                        Icon(Icons.Default.Mic, contentDescription = null, tint = Primary)
                        Spacer(modifier = Modifier.padding(start = 4.dp))
                        Text("Record voice note")
                    }
                    OutlinedButton(
                        onClick = { onManualTextEntry(call.id) },
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(14.dp)
                    ) {
                        Icon(Icons.Default.Edit, contentDescription = null, tint = Primary)
                        Spacer(modifier = Modifier.padding(start = 4.dp))
                        Text("Type manual notes")
                    }
                }

                Spacer(modifier = Modifier.height(20.dp))
                Text(text = "AI Call Brief", style = MaterialTheme.typography.titleMedium)
                Spacer(modifier = Modifier.height(8.dp))
                BriefEditor(uiState, viewModel)

                if (call.needsIdentityResolution) {
                    Spacer(modifier = Modifier.height(20.dp))
                    IdentityResolutionSection(call, uiState, viewModel)
                }

                Spacer(modifier = Modifier.height(24.dp))

                if (uiState.isSubmittingAction) {
                    CircularProgressIndicator(color = Primary)
                } else {
                    CtaButton(
                        text = "Confirm & Log",
                        onClick = viewModel::confirm,
                        enabled = call.canConfirm,
                        modifier = Modifier.fillMaxWidth()
                    )
                    Spacer(modifier = Modifier.height(10.dp))
                    OutlinedButton(
                        onClick = { viewModel.remindLater(null) },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(14.dp)
                    ) {
                        Text("Remind Me Later")
                    }
                }

                Spacer(modifier = Modifier.height(32.dp))
            }
        }
    }
}

@Composable
private fun CallMetadataCard(call: CallSession) {
    Card(
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = Surface),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(text = call.officialName ?: call.phoneRef ?: "Unknown caller", style = MaterialTheme.typography.titleLarge)
            call.phoneRef?.let { Text(text = it, style = MaterialTheme.typography.bodyMedium, color = MutedForeground) }
            Spacer(modifier = Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                StatusBadge(text = call.processingStatus ?: "unknown", tone = processingStatusTone(call.processingStatus))
                StatusBadge(text = call.identityStatus ?: "unidentified", tone = identityStatusTone(call.identityStatus))
            }
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = "Direction: ${call.direction}" + (call.startedAt?.let { " • Started: $it" } ?: ""),
                style = MaterialTheme.typography.bodySmall,
                color = MutedForeground
            )
        }
    }
}

@Composable
private fun TranscriptCard(call: CallSession) {
    Card(
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = Surface),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            if (call.transcriptText.isNullOrBlank()) {
                Text(
                    text = "No transcript yet. Add a voice note or manual notes below to complete this call log.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MutedForeground
                )
            } else {
                call.transcriptSource?.let {
                    Text(text = "Source: $it", style = MaterialTheme.typography.labelSmall, color = MutedForeground)
                    Spacer(modifier = Modifier.height(4.dp))
                }
                Text(text = call.transcriptText, style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}

@Composable
private fun BriefEditor(uiState: CallReviewUiState, viewModel: CallReviewViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        LabeledField("Summary", uiState.summary, viewModel::onSummaryChange, singleLine = false)
        LabeledField("Key points (comma-separated)", uiState.keyPointsText, viewModel::onKeyPointsChange)
        LabeledField("Decisions (comma-separated)", uiState.decisionsText, viewModel::onDecisionsChange)
        LabeledField("Commitments (comma-separated)", uiState.commitmentsText, viewModel::onCommitmentsChange)
        LabeledField("Action items (comma-separated)", uiState.actionItemsText, viewModel::onActionItemsChange)
        LabeledField("Opportunities (comma-separated)", uiState.opportunitiesText, viewModel::onOpportunitiesChange)
        LabeledField("Relationship signals (comma-separated)", uiState.relationshipSignalsText, viewModel::onRelationshipSignalsChange)
        LabeledField("Suggested next interaction", uiState.suggestedNextInteraction, viewModel::onSuggestedNextInteractionChange, singleLine = false)
    }
}

@Composable
private fun LabeledField(
    label: String,
    value: String,
    onChange: (String) -> Unit,
    singleLine: Boolean = true
) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        singleLine = singleLine,
        minLines = if (singleLine) 1 else 2,
        colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Primary),
        modifier = Modifier.fillMaxWidth()
    )
}

@Composable
private fun IdentityResolutionSection(
    call: CallSession,
    uiState: CallReviewUiState,
    viewModel: CallReviewViewModel
) {
    Card(
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = Surface),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(text = "Identity resolution needed", style = MaterialTheme.typography.titleMedium, color = Destructive)
            Spacer(modifier = Modifier.height(6.dp))

            if (call.officialId != null) {
                // Official already matched, just no Relationship row yet - one click, no re-search.
                Text(
                    text = "No relationship on file for ${call.officialName ?: "this official"} yet.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MutedForeground
                )
                Spacer(modifier = Modifier.height(10.dp))
                CtaButton(
                    text = "Create relationship with ${call.officialName ?: "official"}",
                    onClick = viewModel::createRelationshipWithKnownOfficial,
                    modifier = Modifier.fillMaxWidth()
                )
            } else {
                // Genuinely unidentified caller - full resolution flow.
                Text(
                    text = "Who was this call with?",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MutedForeground
                )
                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = uiState.identitySearchQuery,
                    onValueChange = viewModel::onIdentitySearchQueryChange,
                    label = { Text("Search existing officials") },
                    singleLine = true,
                    colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Primary),
                    modifier = Modifier.fillMaxWidth()
                )

                if (uiState.isIdentitySearching) {
                    Spacer(modifier = Modifier.height(8.dp))
                    CircularProgressIndicator(color = Primary)
                }

                uiState.identitySearchResults.forEach { official ->
                    Spacer(modifier = Modifier.height(8.dp))
                    IdentityCandidateRow(official = official, onLink = { viewModel.linkExistingOfficial(official) })
                }

                Spacer(modifier = Modifier.height(14.dp))
                HorizontalDivider()
                Spacer(modifier = Modifier.height(14.dp))

                if (uiState.showCreateOfficialForm) {
                    CreateOfficialForm(
                        onCancel = { viewModel.toggleCreateOfficialForm(false) },
                        onCreate = { name, phone, designation, department, level, location ->
                            viewModel.createNewOfficial(name, phone, designation, department, level, location)
                        }
                    )
                } else {
                    OutlinedButton(
                        onClick = { viewModel.toggleCreateOfficialForm(true) },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(14.dp)
                    ) {
                        Text("Create a new official")
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))
                OutlinedButton(
                    onClick = viewModel::dismissIdentity,
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(14.dp),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = MutedForeground)
                ) {
                    Text("Dismiss / keep unidentified")
                }
            }
        }
    }
}

@Composable
private fun IdentityCandidateRow(official: Official, onLink: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(text = official.name, style = MaterialTheme.typography.titleSmall)
            val subtitle = listOfNotNull(official.designation, official.phone).joinToString(" • ")
            if (subtitle.isNotBlank()) {
                Text(text = subtitle, style = MaterialTheme.typography.bodySmall, color = MutedForeground)
            }
        }
        Button(
            onClick = onLink,
            colors = ButtonDefaults.buttonColors(containerColor = Primary),
            shape = RoundedCornerShape(12.dp)
        ) {
            Text("Link")
        }
    }
}

@Composable
private fun CreateOfficialForm(
    onCancel: () -> Unit,
    onCreate: (name: String, phone: String?, designation: String?, department: String?, level: String?, location: String?) -> Unit
) {
    var name by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var designation by remember { mutableStateOf("") }
    var department by remember { mutableStateOf("") }
    var level by remember { mutableStateOf("") }
    var location by remember { mutableStateOf("") }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(text = "New official", style = MaterialTheme.typography.titleSmall)
        LabeledField("Name *", name, { name = it })
        LabeledField("Phone", phone, { phone = it })
        LabeledField("Designation", designation, { designation = it })
        LabeledField("Department", department, { department = it })
        LabeledField("Level", level, { level = it })
        LabeledField("Location", location, { location = it })
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = onCancel, modifier = Modifier.weight(1f)) {
                Text("Cancel")
            }
            CtaButton(
                text = "Create",
                enabled = name.isNotBlank(),
                onClick = {
                    onCreate(
                        name.trim(),
                        phone.trim().ifBlank { null },
                        designation.trim().ifBlank { null },
                        department.trim().ifBlank { null },
                        level.trim().ifBlank { null },
                        location.trim().ifBlank { null }
                    )
                },
                modifier = Modifier.weight(1f)
            )
        }
    }
}
