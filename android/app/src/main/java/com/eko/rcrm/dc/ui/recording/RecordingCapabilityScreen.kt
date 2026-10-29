package com.eko.rcrm.dc.ui.recording

import android.os.Build
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.eko.rcrm.dc.data.local.PrivilegedMode
import com.eko.rcrm.dc.nativecall.recording.RecordingCapabilityLevel
import com.eko.rcrm.dc.recorder.RecorderBackend
import com.eko.rcrm.dc.ui.common.AppCard
import com.eko.rcrm.dc.ui.common.AppTopBar
import com.eko.rcrm.dc.ui.common.StatusBadge
import com.eko.rcrm.dc.ui.common.Tone
import com.eko.rcrm.dc.ui.theme.Background
import com.eko.rcrm.dc.ui.theme.MutedForeground
import kotlinx.coroutines.delay

/** Shows exactly why native-SIM call recording is, or isn't, available on this device and
 * build - every engine the app could use, not just the active one, so a device-compatibility
 * check can be done without placing a real call. Mirrors the capability check
 * NativeCallForegroundService itself consults before a call. */
@Composable
fun RecordingCapabilityScreen(
    onBack: () -> Unit,
    viewModel: RecordingCapabilityViewModel = hiltViewModel()
) {
    var rows by remember { mutableStateOf(viewModel.snapshot()) }
    var readiness by remember { mutableStateOf(viewModel.readiness()) }
    var mode by remember { mutableStateOf(viewModel.mode()) }
    var offWifiMessage by remember { mutableStateOf<String?>(null) }
    val context = LocalContext.current

    fun refresh() {
        rows = viewModel.snapshot()
        mode = viewModel.mode()
        readiness = viewModel.readiness()
        // The quick value above can be stale (a dead ADB link looks alive); this one probes it.
        viewModel.refreshReadiness { readiness = it; rows = viewModel.snapshot() }
    }

    // Keep the screen honest on its own: after Developer options / Wireless debugging go off, or right after
    // pairing completes in the notification, the state changes without any tap here.
    LaunchedEffect(Unit) {
        while (true) {
            refresh()
            delay(4_000)
        }
    }

    Scaffold(
        containerColor = Background,
        topBar = { AppTopBar(title = "Recording Capability", onBack = onBack) }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(20.dp)
        ) {
            Text(text = "This device", style = MaterialTheme.typography.titleMedium)
            Spacer(modifier = Modifier.height(8.dp))
            DeviceInfoCard()

            Spacer(modifier = Modifier.height(20.dp))
            Text(text = "Two-way recording", style = MaterialTheme.typography.titleMedium)
            Spacer(modifier = Modifier.height(8.dp))
            TwoWaySetupCard(
                mode = mode,
                readiness = readiness,
                onSelectMode = { viewModel.setMode(it); refresh() },
                onOpenWirelessDebugging = {
                    runCatching {
                        context.startActivity(Intent("android.settings.APPLICATION_DEVELOPMENT_SETTINGS"))
                    }.onFailure { runCatching { context.startActivity(Intent(android.provider.Settings.ACTION_DEVICE_INFO_SETTINGS)) } }
                },
                onStartPairing = { viewModel.startEmbeddedPairing() },
                onArmOffWifi = {
                    offWifiMessage = "Arming… keep Wi-Fi on for a few seconds."
                    viewModel.armOffWifi { _, msg -> offWifiMessage = msg; refresh() }
                },
                offWifiMessage = offWifiMessage,
                onInstallShizuku = {
                    val market = Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=moe.shizuku.privileged.api"))
                    val web = Intent(Intent.ACTION_VIEW, Uri.parse("https://shizuku.rikka.app/"))
                    runCatching { context.startActivity(market) }.onFailure { context.startActivity(web) }
                },
                onGrantShizuku = { viewModel.requestShizukuPermission() },
                onRefresh = { refresh() },
            )

            Spacer(modifier = Modifier.height(20.dp))
            Text(text = "Recording engines", style = MaterialTheme.typography.titleMedium)
            Text(
                text = "True two-way capture of a cellular call's own audio is reserved by Android " +
                    "to privileged apps. The privileged engine reaches it via Shizuku where that is " +
                    "set up; otherwise \"Supported\" is not shown and capture falls back to mic-only.",
                style = MaterialTheme.typography.bodySmall,
                color = MutedForeground
            )
            Spacer(modifier = Modifier.height(10.dp))
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                rows.forEach { row -> EngineCard(row) }
            }

            Spacer(modifier = Modifier.height(24.dp))
            AttributionCard()
            Spacer(modifier = Modifier.height(24.dp))
        }
    }
}

@Composable
private fun TwoWaySetupCard(
    mode: PrivilegedMode,
    readiness: RecorderBackend.Readiness,
    onSelectMode: (PrivilegedMode) -> Unit,
    onOpenWirelessDebugging: () -> Unit,
    onStartPairing: () -> Unit,
    onArmOffWifi: () -> Unit,
    offWifiMessage: String?,
    onInstallShizuku: () -> Unit,
    onGrantShizuku: () -> Unit,
    onRefresh: () -> Unit,
) {
    AppCard(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            // Mode picker.
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChipLike("Built-in (no 2nd app)", mode == PrivilegedMode.EMBEDDED_ADB) { onSelectMode(PrivilegedMode.EMBEDDED_ADB) }
                FilterChipLike("Shizuku", mode == PrivilegedMode.SHIZUKU) { onSelectMode(PrivilegedMode.SHIZUKU) }
            }
            Spacer(modifier = Modifier.height(12.dp))

            if (readiness == RecorderBackend.Readiness.READY) {
                Text(text = "Ready", style = MaterialTheme.typography.titleSmall)
                Spacer(modifier = Modifier.height(6.dp))
                Text(
                    text = "Both sides of a call with a CRM official will be recorded on this device.",
                    style = MaterialTheme.typography.bodySmall, color = MutedForeground
                )
                if (mode == PrivilegedMode.EMBEDDED_ADB) {
                    Spacer(modifier = Modifier.height(12.dp))
                    Text(text = "Record without Wi-Fi", style = MaterialTheme.typography.titleSmall)
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "Normally the built-in recorder needs Wi-Fi. Arm this once (on Wi-Fi, with USB " +
                            "debugging ON in Developer options) to keep recording working without Wi-Fi until the " +
                            "phone restarts.",
                        style = MaterialTheme.typography.bodySmall, color = MutedForeground
                    )
                    offWifiMessage?.let {
                        Spacer(modifier = Modifier.height(6.dp))
                        Text(text = it, style = MaterialTheme.typography.bodySmall)
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = onArmOffWifi) { Text("Arm off-Wi-Fi") }
                        TextButton(onClick = onRefresh) { Text("Refresh") }
                    }
                    Spacer(modifier = Modifier.height(12.dp))
                    Text(text = "Connection lost?", style = MaterialTheme.typography.titleSmall)
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "If recording stops working (for example after turning Developer options off), this " +
                            "screen switches to pairing on its own. You can also pair again with a new pairing code.",
                        style = MaterialTheme.typography.bodySmall, color = MutedForeground
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    TextButton(onClick = onStartPairing) { Text("Pair again with code") }
                } else {
                    Spacer(modifier = Modifier.height(8.dp))
                    TextButton(onClick = onRefresh) { Text("Refresh") }
                }
                return@Column
            }

            when (mode) {
                PrivilegedMode.EMBEDDED_ADB -> {
                    Text(text = "Pair the built-in recorder", style = MaterialTheme.typography.titleSmall)
                    Spacer(modifier = Modifier.height(6.dp))
                    Text(
                        text = "No second app. Do it in this order:\n" +
                            "1. Tap Start pairing below.\n" +
                            "2. Open Developer options ▸ turn on Wireless debugging.\n" +
                            "3. Tap \"Pair device with pairing code\" — a 6-digit code shows. Keep it open.\n" +
                            "4. Pull down the notification shade: this app's notification says \"Enter the pairing code\". " +
                            "Type the 6-digit code INTO THE NOTIFICATION (not here) and send.\n" +
                            "5. Come back and tap Refresh — it should say Ready.",
                        style = MaterialTheme.typography.bodySmall, color = MutedForeground
                    )
                    Spacer(modifier = Modifier.height(10.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = onStartPairing) { Text("Start pairing") }
                        TextButton(onClick = onOpenWirelessDebugging) { Text("Developer options") }
                        TextButton(onClick = onRefresh) { Text("Refresh") }
                    }
                }
                PrivilegedMode.SHIZUKU -> {
                    val (title, body) = when (readiness) {
                        RecorderBackend.Readiness.SHIZUKU_NOT_INSTALLED ->
                            "Install Shizuku" to "The Shizuku mode needs the free Shizuku app. Install it, then return here."
                        RecorderBackend.Readiness.SHIZUKU_NOT_RUNNING ->
                            "Start Shizuku" to "Shizuku is installed but not running. Start its service, then refresh."
                        RecorderBackend.Readiness.NO_PERMISSION ->
                            "Allow recording" to "Grant this app permission in Shizuku, then refresh."
                        else -> "Set up Shizuku" to "Follow Shizuku's setup, then refresh."
                    }
                    Text(text = title, style = MaterialTheme.typography.titleSmall)
                    Spacer(modifier = Modifier.height(6.dp))
                    Text(text = body, style = MaterialTheme.typography.bodySmall, color = MutedForeground)
                    Spacer(modifier = Modifier.height(12.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        when (readiness) {
                            RecorderBackend.Readiness.SHIZUKU_NOT_INSTALLED -> Button(onClick = onInstallShizuku) { Text("Install Shizuku") }
                            RecorderBackend.Readiness.NO_PERMISSION -> Button(onClick = onGrantShizuku) { Text("Allow in Shizuku") }
                            else -> Unit
                        }
                        TextButton(onClick = onRefresh) { Text("Refresh") }
                    }
                }
            }
        }
    }
}

@Composable
private fun FilterChipLike(label: String, selected: Boolean, onClick: () -> Unit) {
    if (selected) Button(onClick = onClick) { Text(label) }
    else TextButton(onClick = onClick) { Text(label) }
}

/** GPL-3.0 Section 7 attribution: the privileged recorder is derived from CallVault, a fork of
 * ShizuCallRecorder. This notice is required to be visible in the app. */
@Composable
private fun AttributionCard() {
    AppCard(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(text = "Open-source notice", style = MaterialTheme.typography.titleSmall)
            Spacer(modifier = Modifier.height(6.dp))
            Text(
                text = "The two-way call recorder is derived from CallVault, a fork of ShizuCallRecorder " +
                    "(https://github.com/kitsumed/ShizuCallRecorder), licensed under the GNU General " +
                    "Public License v3. This app is therefore distributed under GPL-3.0; the corresponding " +
                    "source is available with this build.",
                style = MaterialTheme.typography.bodySmall,
                color = MutedForeground
            )
        }
    }
}

@Composable
private fun DeviceInfoCard() {
    AppCard(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            InfoRow("Manufacturer", Build.MANUFACTURER)
            InfoRow("Model", Build.MODEL)
            InfoRow("Android version", Build.VERSION.RELEASE)
            InfoRow("SDK level", Build.VERSION.SDK_INT.toString())
        }
    }
}

@Composable
private fun InfoRow(label: String, value: String) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(text = label, style = MaterialTheme.typography.bodyMedium, color = MutedForeground)
        Text(text = value, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun EngineCard(row: EngineCapabilityRow) {
    AppCard(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(text = row.engineId, style = MaterialTheme.typography.titleSmall)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    if (row.isActive) StatusBadge(text = "Active", tone = Tone.Primary)
                    StatusBadge(text = levelLabel(row.capability.level), tone = levelTone(row.capability.level))
                }
            }
            Spacer(modifier = Modifier.height(8.dp))
            Text(text = row.capability.reason, style = MaterialTheme.typography.bodySmall, color = MutedForeground)
        }
    }
}

private fun levelLabel(level: RecordingCapabilityLevel): String = when (level) {
    RecordingCapabilityLevel.SUPPORTED -> "Supported"
    RecordingCapabilityLevel.PARTIALLY_SUPPORTED -> "Partially supported"
    RecordingCapabilityLevel.UNSUPPORTED -> "Unsupported"
    RecordingCapabilityLevel.UNKNOWN -> "Unknown"
}

private fun levelTone(level: RecordingCapabilityLevel): Tone = when (level) {
    RecordingCapabilityLevel.SUPPORTED -> Tone.Good
    RecordingCapabilityLevel.PARTIALLY_SUPPORTED -> Tone.Warn
    RecordingCapabilityLevel.UNSUPPORTED -> Tone.Neutral
    RecordingCapabilityLevel.UNKNOWN -> Tone.Neutral
}
