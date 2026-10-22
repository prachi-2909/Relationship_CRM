package com.eko.rcrm.dc.ui.manualdial

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Dialpad
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.eko.rcrm.dc.nativecall.rememberNativeCallLauncher
import com.eko.rcrm.dc.ui.common.AppTopBar
import com.eko.rcrm.dc.ui.common.CtaButton
import com.eko.rcrm.dc.ui.common.ErrorBanner
import com.eko.rcrm.dc.ui.theme.Background
import com.eko.rcrm.dc.ui.theme.MutedForeground
import com.eko.rcrm.dc.ui.theme.Primary

@Composable
fun ManualDialScreen(
    onBack: () -> Unit,
    onCallStarted: (Int) -> Unit,
    viewModel: ManualDialViewModel = hiltViewModel()
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

    Scaffold(
        containerColor = Background,
        topBar = { AppTopBar(title = "Dial a Number", onBack = onBack) }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(20.dp)
        ) {
            Icon(Icons.Default.Dialpad, contentDescription = null, tint = Primary)
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = "Calls the same way as a saved official - through Knowlarity, or your own SIM if that's how this app is configured.",
                style = MaterialTheme.typography.bodySmall,
                color = MutedForeground
            )
            Spacer(modifier = Modifier.height(20.dp))

            OutlinedTextField(
                value = uiState.number,
                onValueChange = viewModel::onNumberChange,
                placeholder = { Text("Enter phone number") },
                singleLine = true,
                keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(keyboardType = KeyboardType.Phone),
                colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Primary),
                modifier = Modifier.fillMaxWidth()
            )

            (uiState.error ?: permissionError)?.let {
                Spacer(modifier = Modifier.height(12.dp))
                ErrorBanner(message = it)
            }

            Spacer(modifier = Modifier.height(20.dp))

            if (uiState.isCalling) {
                CircularProgressIndicator(color = Primary)
            } else {
                CtaButton(text = "Call", onClick = viewModel::call, modifier = Modifier.fillMaxWidth())
            }
        }
    }
}
