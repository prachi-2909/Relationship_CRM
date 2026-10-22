package com.eko.rcrm.dc.ui.profile

import android.app.role.RoleManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.eko.rcrm.dc.domain.model.DcProfile
import com.eko.rcrm.dc.domain.model.DcTerritory
import com.eko.rcrm.dc.ui.common.AppCard
import com.eko.rcrm.dc.ui.common.AppTopBar
import com.eko.rcrm.dc.ui.common.ErrorBanner
import com.eko.rcrm.dc.ui.common.LoadingIndicator
import com.eko.rcrm.dc.ui.common.StatusBadge
import com.eko.rcrm.dc.ui.common.Tone
import com.eko.rcrm.dc.ui.theme.Accent
import com.eko.rcrm.dc.ui.theme.Background
import com.eko.rcrm.dc.ui.theme.MutedForeground
import com.eko.rcrm.dc.ui.theme.Primary

@Composable
fun ProfileScreen(
    onBack: () -> Unit,
    onOpenUnit: (Int, String) -> Unit,
    onOpenRecordingCapability: () -> Unit,
    viewModel: ProfileViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    val recordCalls by viewModel.recordCalls.collectAsState()
    val detection by viewModel.detection.collectAsState()

    Scaffold(
        containerColor = Background,
        topBar = { AppTopBar(title = "My Profile", onBack = onBack) }
    ) { padding ->
        val profile = uiState.profile
        when {
            uiState.isLoading && profile == null -> LoadingIndicator(modifier = Modifier.padding(padding))
            profile == null -> ErrorBanner(
                message = uiState.error ?: "Could not load your profile.",
                modifier = Modifier.padding(padding).padding(20.dp)
            )
            else -> ProfileContent(
                profile = profile,
                onOpenUnit = onOpenUnit,
                recordCalls = recordCalls,
                onRecordCallsChange = viewModel::setRecordCalls,
                detection = detection,
                onDetectionRefresh = viewModel::refreshDetection,
                onOpenRecordingCapability = onOpenRecordingCapability,
                modifier = Modifier.padding(padding)
            )
        }
    }
}


@Composable
private fun AutoDetectCard(detection: ProfileViewModel.DetectionSnapshot, onRefresh: () -> Unit) {
    val context = LocalContext.current
    val supported = Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q
    var refreshKey by remember { mutableIntStateOf(0) }
    val roleManager = remember { if (supported) context.getSystemService(RoleManager::class.java) else null }
    val held = remember(refreshKey) {
        supported && roleManager?.isRoleHeld(RoleManager.ROLE_CALL_SCREENING) == true
    }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        refreshKey++
    }
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                refreshKey++
                onRefresh()
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    AppCard(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Auto-detect calls with CRM contacts",
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.weight(1f).padding(end = 8.dp)
                )
                if (held) StatusBadge(text = "On", tone = Tone.Good)
            }
            Spacer(modifier = Modifier.height(4.dp))
            when {
                !supported -> Text(
                    text = "Needs Android 10 or newer.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MutedForeground
                )
                held -> {
                    Text(
                        text = "Calls you make or receive on this phone with officials in your territory are added " +
                            "to your Pending Queue automatically. Other calls are never uploaded.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MutedForeground
                    )
                    detection.message?.let { message ->
                        Spacer(modifier = Modifier.height(8.dp))
                        val seenAt = DateTimeFormatter.ofPattern("dd MMM, hh:mm a", Locale.ENGLISH)
                            .format(Instant.ofEpochMilli(detection.atMs).atZone(ZoneId.systemDefault()))
                        Text(
                            text = "Last call seen (" + seenAt + "):",
                            style = MaterialTheme.typography.labelSmall,
                            color = MutedForeground
                        )
                        Text(text = message, style = MaterialTheme.typography.bodySmall)
                    }
                }
                else -> {
                    Text(
                        text = "Lets the app notice calls you make or receive on this phone with officials in your " +
                            "territory and add them to your Pending Queue. It never blocks or changes a call, and " +
                            "calls with anyone who isn't in the CRM are never uploaded.\n\n" +
                            "Heads up: Android allows only one Caller ID and spam app, so enabling this replaces the " +
                            "current one (for example Google's).",
                        style = MaterialTheme.typography.bodySmall,
                        color = MutedForeground
                    )
                    Spacer(modifier = Modifier.height(10.dp))
                    TextButton(onClick = {
                        roleManager?.let { launcher.launch(it.createRequestRoleIntent(RoleManager.ROLE_CALL_SCREENING)) }
                    }) { Text("Enable") }
                }
            }
        }
    }
}

@Composable
private fun RecordCallsCard(recordCalls: Boolean, onChange: (Boolean) -> Unit) {
    var showConsent by remember { mutableStateOf(false) }

    AppCard(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f).padding(end = 12.dp)) {
                Text(text = "Record my calls", style = MaterialTheme.typography.titleMedium)
                Text(
                    text = "Records calls with CRM officials (both sides when two-way recording is set up on the Recording capability screen). Only CRM-contact calls are ever recorded.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MutedForeground
                )
            }
            Switch(
                checked = recordCalls,
                onCheckedChange = { wantsOn -> if (wantsOn) showConsent = true else onChange(false) }
            )
        }
    }

    if (showConsent) {
        AlertDialog(
            onDismissRequest = { showConsent = false },
            title = { Text("Record your calls?") },
            text = {
                Text(
                    "Calls you place from this app will be recorded using your microphone and " +
                        "uploaded to the CRM for transcription.\n\n" +
                        "You must tell the other person that the call is being recorded. " +
                        "Recording someone without their knowledge may be illegal."
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    showConsent = false
                    onChange(true)
                }) { Text("I understand, turn on") }
            },
            dismissButton = {
                TextButton(onClick = { showConsent = false }) { Text("Cancel") }
            }
        )
    }
}

@Composable
private fun ProfileContent(
    profile: DcProfile,
    onOpenUnit: (Int, String) -> Unit,
    recordCalls: Boolean,
    onRecordCallsChange: (Boolean) -> Unit,
    detection: ProfileViewModel.DetectionSnapshot,
    onDetectionRefresh: () -> Unit,
    onOpenRecordingCapability: () -> Unit,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(20.dp)
    ) {
        Text(text = profile.name, style = MaterialTheme.typography.headlineSmall)
        profile.email?.let {
            Text(text = it, style = MaterialTheme.typography.bodyMedium, color = MutedForeground)
        }
        profile.status?.let {
            Spacer(modifier = Modifier.height(6.dp))
            StatusBadge(text = it, tone = if (it == "active") Tone.Good else Tone.Neutral)
        }

        Spacer(modifier = Modifier.height(20.dp))

        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            StatTile(
                label = "Pending calls",
                value = profile.pendingCalls,
                valueColor = if (profile.pendingCalls > 0) Primary else Accent,
                modifier = Modifier.weight(1f)
            )
            StatTile(
                label = "Logged interactions",
                value = profile.loggedInteractions,
                valueColor = Accent,
                modifier = Modifier.weight(1f)
            )
        }

        Spacer(modifier = Modifier.height(20.dp))
        AutoDetectCard(detection = detection, onRefresh = onDetectionRefresh)

        Spacer(modifier = Modifier.height(12.dp))
        RecordCallsCard(recordCalls = recordCalls, onChange = onRecordCallsChange)

        Spacer(modifier = Modifier.height(12.dp))
        AppCard(onClick = onOpenRecordingCapability, modifier = Modifier.fillMaxWidth()) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(16.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text(text = "Recording capability", style = MaterialTheme.typography.titleMedium)
                    Text(
                        text = "See which recording engine is active on this device, and why.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MutedForeground
                    )
                }
            }
        }

        Spacer(modifier = Modifier.height(24.dp))
        Text(text = "My Territory", style = MaterialTheme.typography.titleMedium)
        Spacer(modifier = Modifier.height(10.dp))

        if (profile.territory.isEmpty()) {
            Text(
                text = "No organisation units assigned yet.",
                style = MaterialTheme.typography.bodyMedium,
                color = MutedForeground
            )
        } else {
            Text(
                text = "Tap a unit to see its officials",
                style = MaterialTheme.typography.bodySmall,
                color = MutedForeground
            )
            Spacer(modifier = Modifier.height(8.dp))
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                profile.territory.forEach { unit ->
                    TerritoryRow(unit, onClick = { onOpenUnit(unit.organizationUnitId, unit.organizationUnitName) })
                }
            }
        }
    }
}

@Composable
private fun StatTile(label: String, value: Int, valueColor: androidx.compose.ui.graphics.Color, modifier: Modifier = Modifier) {
    AppCard(modifier = modifier) {
        Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
            Text(text = label, style = MaterialTheme.typography.bodySmall, color = MutedForeground)
            Text(text = "$value", style = MaterialTheme.typography.headlineMedium, color = valueColor)
        }
    }
}

@Composable
private fun TerritoryRow(unit: DcTerritory, onClick: () -> Unit) {
    AppCard(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Column {
                Text(text = unit.organizationUnitName, style = MaterialTheme.typography.titleMedium)
                if (!unit.isDirect) {
                    Text(
                        text = "Shared area official",
                        style = MaterialTheme.typography.labelSmall,
                        color = MutedForeground
                    )
                }
            }
            StatusBadge(text = unit.organizationUnitType, tone = Tone.Primary)
        }
    }
}
