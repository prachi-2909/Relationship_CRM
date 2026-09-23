package com.eko.rcrm.dc.ui.voicenote

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.eko.rcrm.dc.ui.common.AppTopBar
import com.eko.rcrm.dc.ui.common.CtaButton
import com.eko.rcrm.dc.ui.common.ErrorBanner
import com.eko.rcrm.dc.ui.theme.Accent
import com.eko.rcrm.dc.ui.theme.Background
import com.eko.rcrm.dc.ui.theme.Destructive
import com.eko.rcrm.dc.ui.theme.MutedForeground
import com.eko.rcrm.dc.ui.theme.Primary

@Composable
fun VoiceNoteRecordingScreen(
    onBack: () -> Unit,
    onSaved: () -> Unit,
    viewModel: VoiceNoteRecordingViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    val context = LocalContext.current

    var hasPermission by remember {
        mutableStateOf(
            androidx.core.content.ContextCompat.checkSelfPermission(
                context,
                Manifest.permission.RECORD_AUDIO
            ) == PackageManager.PERMISSION_GRANTED
        )
    }
    var permissionDenied by remember { mutableStateOf(false) }

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        hasPermission = granted
        permissionDenied = !granted
        if (granted) viewModel.startRecording()
    }

    LaunchedEffect(uiState.stage) {
        if (uiState.stage == VoiceNoteStage.UPLOADED_DIRECT || uiState.stage == VoiceNoteStage.QUEUED_OFFLINE) {
            onSaved()
        }
    }

    Scaffold(
        containerColor = Background,
        topBar = { AppTopBar(title = "Record Voice Note", onBack = onBack) }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                text = "Record a short recap of the call - this is your fallback if the " +
                    "call recording didn't come through.",
                style = MaterialTheme.typography.bodyMedium,
                color = MutedForeground
            )

            Spacer(modifier = Modifier.height(32.dp))

            if (permissionDenied) {
                ErrorBanner(message = "Microphone permission is required to record a voice note.")
                Spacer(modifier = Modifier.height(16.dp))
            }
            uiState.error?.let {
                ErrorBanner(message = it)
                Spacer(modifier = Modifier.height(16.dp))
            }

            Box(
                modifier = Modifier
                    .size(140.dp)
                    .weight(1f, fill = false),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = VoiceNoteRecordingViewModel.formatElapsed(uiState.elapsedSeconds),
                    style = MaterialTheme.typography.headlineMedium
                )
            }

            Spacer(modifier = Modifier.height(24.dp))

            when (uiState.stage) {
                VoiceNoteStage.IDLE -> {
                    IconButton(
                        onClick = {
                            if (hasPermission) {
                                viewModel.startRecording()
                            } else {
                                permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                            }
                        },
                        colors = IconButtonDefaults.iconButtonColors(containerColor = Primary),
                        modifier = Modifier.size(72.dp)
                    ) {
                        Icon(Icons.Default.Mic, contentDescription = "Start recording", tint = androidx.compose.ui.graphics.Color.White)
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                    Text("Tap to start recording", style = MaterialTheme.typography.bodySmall, color = MutedForeground)
                }

                VoiceNoteStage.RECORDING -> {
                    IconButton(
                        onClick = viewModel::stopRecording,
                        colors = IconButtonDefaults.iconButtonColors(containerColor = Destructive),
                        modifier = Modifier.size(72.dp)
                    ) {
                        Icon(Icons.Default.Stop, contentDescription = "Stop recording", tint = androidx.compose.ui.graphics.Color.White)
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                    Text("Recording... tap to stop", style = MaterialTheme.typography.bodySmall, color = MutedForeground)
                }

                VoiceNoteStage.RECORDED -> {
                    Text("Recording captured (${VoiceNoteRecordingViewModel.formatElapsed(uiState.elapsedSeconds)})", color = Accent)
                    Spacer(modifier = Modifier.height(16.dp))
                    CtaButton(text = "Save & Upload", onClick = viewModel::saveAndUpload, modifier = Modifier.fillMaxWidth())
                    Spacer(modifier = Modifier.height(10.dp))
                    OutlinedButton(onClick = viewModel::discardRecording, modifier = Modifier.fillMaxWidth()) {
                        Text("Discard & re-record")
                    }
                }

                VoiceNoteStage.UPLOADING -> {
                    CircularProgressIndicator(color = Primary)
                    Spacer(modifier = Modifier.height(8.dp))
                    Text("Uploading...", color = MutedForeground)
                }

                VoiceNoteStage.UPLOADED_DIRECT, VoiceNoteStage.QUEUED_OFFLINE -> {
                    CircularProgressIndicator(color = Primary)
                }
            }
        }
    }
}
