package com.eko.rcrm.dc.ui.home

import android.content.Intent
import android.os.Build
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Dialpad
import androidx.compose.material.icons.filled.EditNote
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Logout
import androidx.compose.material.icons.filled.People
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.SystemUpdate
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.hilt.navigation.compose.hiltViewModel
import com.eko.rcrm.dc.ui.common.AppCard
import com.eko.rcrm.dc.ui.common.CtaButton
import com.eko.rcrm.dc.ui.common.HeroStatCard
import com.eko.rcrm.dc.ui.common.IconTile
import com.eko.rcrm.dc.ui.theme.Background
import com.eko.rcrm.dc.ui.theme.MutedForeground
import com.eko.rcrm.dc.ui.theme.Primary
import com.eko.rcrm.dc.ui.theme.Saffron
import java.io.File

@Composable
fun HomeScreen(
    onSearchOfficials: () -> Unit,
    onAllOfficials: () -> Unit,
    onManualDial: () -> Unit,
    onLogCall: () -> Unit,
    onCalls: () -> Unit,
    onProfile: () -> Unit,
    onMyCsps: () -> Unit,
    onLoggedOut: () -> Unit,
    viewModel: HomeViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    val context = LocalContext.current

    LaunchedEffect(uiState.loggedOut) {
        if (uiState.loggedOut) onLoggedOut()
    }

    // Relationship Manager: consent to all-call recording is asked up front, before any call is
    // recorded. Agreeing turns recording on; dismissing leaves it off until they consent later.
    if (uiState.showRmConsent) {
        AlertDialog(
            onDismissRequest = viewModel::onRmConsentDismiss,
            title = { Text("Record your CSP calls?") },
            text = {
                Text(
                    "As a Relationship Manager, your calls with your CSPs — on their primary or " +
                        "alternate number, whether you call them or they call you — will be recorded " +
                        "and securely transcribed into the CRM, and kept there. Your personal calls " +
                        "(any number that is not a CSP's) are never recorded. Please make sure the CSP " +
                        "is informed that the call is being recorded. You can turn this off anytime from " +
                        "your Profile."
                )
            },
            confirmButton = {
                TextButton(onClick = viewModel::onRmRecordingConsent) { Text("I agree, record CSP calls") }
            },
            dismissButton = {
                TextButton(onClick = viewModel::onRmConsentDismiss) { Text("Not now") }
            }
        )
    }

    // A new version is on the server: say so up front. "Update" downloads it and hands it to Android's installer
    // (one confirmation tap there); "Later" leaves the banner on this screen. Not shown over the consent dialog.
    val update = uiState.updateAvailable
    if (update != null && !uiState.updateDialogDismissed && !uiState.showRmConsent) {
        AlertDialog(
            onDismissRequest = { if (!uiState.isDownloadingUpdate) viewModel.onUpdateDialogLater() },
            title = { Text("Update available") },
            text = {
                Column {
                    Text("Version ${update.versionName} is ready. Update now?")
                    if (uiState.isDownloadingUpdate) {
                        Spacer(modifier = Modifier.height(12.dp))
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            CircularProgressIndicator(color = Primary, modifier = Modifier.size(20.dp), strokeWidth = 2.dp)
                            Text(text = "Downloading...", modifier = Modifier.padding(start = 12.dp))
                        }
                    }
                    uiState.updateError?.let {
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(text = it, style = MaterialTheme.typography.bodySmall, color = MutedForeground)
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = viewModel::downloadUpdate, enabled = !uiState.isDownloadingUpdate) {
                    Text("Update")
                }
            },
            dismissButton = {
                TextButton(onClick = viewModel::onUpdateDialogLater, enabled = !uiState.isDownloadingUpdate) {
                    Text("Later")
                }
            }
        )
    }

    // One confirmation tap to install, never silent - Android has no silent-install path for a
    // non-Play-Store, non-MDM-enrolled app, so handing off to the system installer is as far as
    // this can go automatically.
    LaunchedEffect(uiState.downloadedApkPath) {
        val path = uiState.downloadedApkPath ?: return@LaunchedEffect
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
            !context.packageManager.canRequestPackageInstalls()
        ) {
            viewModel.onInstallPermissionMissing()
            return@LaunchedEffect
        }
        val file = File(path)
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(intent)
        viewModel.onUpdateInstallLaunched()
    }

    Scaffold(containerColor = Background) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 20.dp)
        ) {
            Spacer(modifier = Modifier.height(20.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top
            ) {
                Column {
                    Text(text = "Welcome back", style = MaterialTheme.typography.bodyMedium, color = MutedForeground)
                    Text(
                        text = uiState.userName ?: "Field DC",
                        style = MaterialTheme.typography.headlineSmall
                    )
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    RoundIconButton(icon = Icons.Default.Person, contentDescription = "My Profile", onClick = onProfile)
                    RoundIconButton(icon = Icons.Default.Logout, contentDescription = "Log out", onClick = viewModel::logout)
                }
            }

            uiState.updateAvailable?.let { info ->
                Spacer(modifier = Modifier.height(16.dp))
                UpdateBanner(
                    versionName = info.versionName,
                    isDownloading = uiState.isDownloadingUpdate,
                    error = uiState.updateError,
                    onUpdateClick = viewModel::downloadUpdate
                )
            }

            Spacer(modifier = Modifier.height(20.dp))

            HeroStatCard(label = "Calls awaiting review", value = uiState.pendingCount, icon = Icons.Default.Call)

            Spacer(modifier = Modifier.height(20.dp))

            // An RM works with their CSPs, not SBI officials - so every "officials" entry point
            // routes to the CSP list for an RM (SBI officials stay DC-only).
            CtaButton(
                text = if (uiState.isRm) "Call a CSP" else "Call an official",
                onClick = if (uiState.isRm) onMyCsps else onSearchOfficials,
                modifier = Modifier.fillMaxWidth()
            )

            Spacer(modifier = Modifier.height(24.dp))

            Text(text = "Quick actions", style = MaterialTheme.typography.titleSmall, color = MutedForeground)
            Spacer(modifier = Modifier.height(10.dp))

            LazyVerticalGrid(
                columns = GridCells.Fixed(2),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
                modifier = Modifier.height(206.dp)
            ) {
                items(quickActions(uiState.pendingCount)) { action ->
                    IconTile(
                        icon = action.icon,
                        label = if (uiState.isRm && action.label == "All officials") "My CSPs" else action.label,
                        iconTint = action.iconTint,
                        iconBackground = action.iconBackground,
                        badgeCount = action.badgeCount,
                        onClick = when (action.label) {
                            "Dial a number" -> onManualDial
                            "Log a call" -> onLogCall
                            // RM: "All officials" points at their CSPs instead of SBI officials.
                            "All officials" -> if (uiState.isRm) onMyCsps else onAllOfficials
                            else -> onCalls   // "Calls" (pending + history)
                        }
                    )
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            AppCard(onClick = if (uiState.isRm) onMyCsps else onSearchOfficials, modifier = Modifier.fillMaxWidth()) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Icon(Icons.Default.Search, contentDescription = null, tint = MutedForeground)
                    Text(
                        text = if (uiState.isRm) "Find a CSP by name or number" else "Search by name, phone, designation",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MutedForeground
                    )
                }
            }

            Spacer(modifier = Modifier.height(20.dp))
        }
    }
}

private data class QuickAction(
    val label: String,
    val icon: androidx.compose.ui.graphics.vector.ImageVector,
    val iconTint: Color,
    val iconBackground: Color,
    val badgeCount: Int? = null
)

private fun quickActions(pendingCount: Int): List<QuickAction> = listOf(
    QuickAction("Dial a number", Icons.Default.Dialpad, Color(0xFF0092CC), Color(0xFFE6F1FB)),
    QuickAction("All officials", Icons.Default.People, Color(0xFF1F6548), Color(0xFFE1F5EE)),
    QuickAction("Calls", Icons.Default.History, Color(0xFF854F0B), Color(0xFFFAEEDA), badgeCount = pendingCount),
    QuickAction("Log a call", Icons.Default.EditNote, Color(0xFF5B4BA8), Color(0xFFEEEDFE))
)

@Composable
private fun RoundIconButton(icon: androidx.compose.ui.graphics.vector.ImageVector, contentDescription: String, onClick: () -> Unit) {
    Box(
        modifier = Modifier
            .size(36.dp)
            .background(MaterialTheme.colorScheme.surface, CircleShape)
            .then(Modifier),
        contentAlignment = Alignment.Center
    ) {
        IconButton(onClick = onClick, modifier = Modifier.size(36.dp)) {
            Icon(icon, contentDescription = contentDescription, tint = MutedForeground, modifier = Modifier.size(18.dp))
        }
    }
}

/** Non-blocking - the DC can keep using the app while an update sits here waiting for a tap. */
@Composable
private fun UpdateBanner(
    versionName: String,
    isDownloading: Boolean,
    error: String?,
    onUpdateClick: () -> Unit
) {
    AppCard(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Row {
                    Icon(Icons.Default.SystemUpdate, contentDescription = null, tint = Saffron)
                    Text(
                        text = "Update available - v$versionName",
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.padding(start = 8.dp)
                    )
                }
                error?.let {
                    Text(text = it, style = MaterialTheme.typography.bodySmall, color = MutedForeground)
                }
            }
            if (isDownloading) {
                CircularProgressIndicator(color = Primary, modifier = Modifier.padding(start = 12.dp))
            } else {
                CtaButton(text = "Update", onClick = onUpdateClick)
            }
        }
    }
}
