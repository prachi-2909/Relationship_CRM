package com.eko.rcrm.dc.ui.manuallog

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.eko.rcrm.dc.ui.common.AppCard
import com.eko.rcrm.dc.ui.common.AppTopBar
import com.eko.rcrm.dc.ui.common.CtaButton
import com.eko.rcrm.dc.ui.common.ErrorBanner
import com.eko.rcrm.dc.ui.theme.Background
import com.eko.rcrm.dc.ui.theme.MutedForeground
import com.eko.rcrm.dc.ui.theme.Primary

@Composable
fun ManualLogScreen(
    onBack: () -> Unit,
    onLogged: (Int) -> Unit,
    viewModel: ManualLogViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()

    LaunchedEffect(Unit) {
        viewModel.navigateToReview.collect { callSessionId -> onLogged(callSessionId) }
    }

    Scaffold(
        containerColor = Background,
        topBar = { AppTopBar(title = "Log a call", onBack = onBack) }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(20.dp)
        ) {
            Text(
                text = "For a call you made or received on this phone outside the app. " +
                    "It goes to your Pending Queue so you can add a recap.",
                style = MaterialTheme.typography.bodySmall,
                color = MutedForeground
            )
            Spacer(modifier = Modifier.height(16.dp))

            if (uiState.phone.isEmpty()) {
                OutlinedTextField(
                    value = uiState.query,
                    onValueChange = viewModel::onQueryChange,
                    placeholder = { Text("Search an official, or type a phone number") },
                    leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
                    singleLine = true,
                    colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Primary),
                    modifier = Modifier.fillMaxWidth()
                )
                if (uiState.isSearching) {
                    Spacer(modifier = Modifier.height(12.dp))
                    CircularProgressIndicator(color = Primary)
                }
                val typedDigits = uiState.query.filter { it.isDigit() }
                Column(
                    modifier = Modifier.padding(top = 10.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    if (typedDigits.length >= 10) {
                        AppCard(onClick = { viewModel.useTypedNumber(typedDigits) }, modifier = Modifier.fillMaxWidth()) {
                            Text(
                                text = "Use number $typedDigits",
                                style = MaterialTheme.typography.titleSmall,
                                modifier = Modifier.padding(14.dp)
                            )
                        }
                    }
                    uiState.results.forEach { official ->
                        AppCard(onClick = { viewModel.selectOfficial(official) }, modifier = Modifier.fillMaxWidth()) {
                            Column(modifier = Modifier.padding(14.dp)) {
                                Text(text = official.name, style = MaterialTheme.typography.titleSmall)
                                val detail = listOfNotNull(official.designation, official.phone).joinToString(" - ")
                                if (detail.isNotBlank()) {
                                    Text(text = detail, style = MaterialTheme.typography.bodySmall, color = MutedForeground)
                                }
                            }
                        }
                    }
                }
            } else {
                AppCard(modifier = Modifier.fillMaxWidth()) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(start = 14.dp, top = 6.dp, bottom = 6.dp, end = 6.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column {
                            Text(text = uiState.selectedName ?: "Unknown number", style = MaterialTheme.typography.titleSmall)
                            Text(text = uiState.phone, style = MaterialTheme.typography.bodySmall, color = MutedForeground)
                        }
                        TextButton(onClick = viewModel::clearSelection) { Text("Change") }
                    }
                }
            }

            Spacer(modifier = Modifier.height(20.dp))
            Text(text = "Direction", style = MaterialTheme.typography.labelLarge)
            Spacer(modifier = Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                FilterChip(
                    selected = !uiState.outgoing,
                    onClick = { viewModel.setOutgoing(false) },
                    label = { Text("They called me") }
                )
                FilterChip(
                    selected = uiState.outgoing,
                    onClick = { viewModel.setOutgoing(true) },
                    label = { Text("I called them") }
                )
            }

            Spacer(modifier = Modifier.height(20.dp))
            OutlinedTextField(
                value = uiState.durationMinutes,
                onValueChange = viewModel::onDurationChange,
                label = { Text("How long was the call? (minutes, optional)") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Primary),
                modifier = Modifier.fillMaxWidth()
            )

            uiState.error?.let {
                Spacer(modifier = Modifier.height(12.dp))
                ErrorBanner(message = it)
            }

            Spacer(modifier = Modifier.height(24.dp))
            if (uiState.isSubmitting) {
                CircularProgressIndicator(color = Primary)
            } else {
                CtaButton(
                    text = "Log call",
                    onClick = viewModel::submit,
                    enabled = uiState.canSubmit,
                    modifier = Modifier.fillMaxWidth()
                )
            }
        }
    }
}
