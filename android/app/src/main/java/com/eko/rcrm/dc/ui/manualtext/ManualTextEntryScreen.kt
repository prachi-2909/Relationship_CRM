package com.eko.rcrm.dc.ui.manualtext

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.eko.rcrm.dc.ui.common.AppTopBar
import com.eko.rcrm.dc.ui.common.CtaButton
import com.eko.rcrm.dc.ui.common.ErrorBanner
import com.eko.rcrm.dc.ui.theme.Background
import com.eko.rcrm.dc.ui.theme.MutedForeground
import com.eko.rcrm.dc.ui.theme.Primary

@Composable
fun ManualTextEntryScreen(
    onBack: () -> Unit,
    onSaved: () -> Unit,
    viewModel: ManualTextEntryViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()

    LaunchedEffect(uiState.saved) {
        if (uiState.saved) onSaved()
    }

    Scaffold(
        containerColor = Background,
        topBar = { AppTopBar(title = "Manual Call Notes", onBack = onBack) }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(20.dp)
        ) {
            Text(
                text = "No recording or voice note? Type what was discussed instead - " +
                    "a recording failure should never stop this call from being logged.",
                style = MaterialTheme.typography.bodyMedium,
                color = MutedForeground
            )

            Spacer(modifier = Modifier.height(16.dp))

            OutlinedTextField(
                value = uiState.text,
                onValueChange = viewModel::onTextChange,
                label = { Text("Call notes") },
                minLines = 8,
                colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Primary),
                modifier = Modifier.fillMaxWidth()
            )

            uiState.error?.let {
                Spacer(modifier = Modifier.height(12.dp))
                ErrorBanner(message = it)
            }

            Spacer(modifier = Modifier.height(20.dp))

            if (uiState.isSubmitting) {
                CircularProgressIndicator(color = Primary)
            } else {
                CtaButton(text = "Save Notes", onClick = viewModel::save, modifier = Modifier.fillMaxWidth())
            }
        }
    }
}
