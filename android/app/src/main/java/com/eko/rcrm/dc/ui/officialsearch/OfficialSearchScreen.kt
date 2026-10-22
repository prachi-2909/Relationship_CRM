package com.eko.rcrm.dc.ui.officialsearch

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.PersonAdd
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.eko.rcrm.dc.domain.model.Official
import com.eko.rcrm.dc.nativecall.rememberNativeCallLauncher
import com.eko.rcrm.dc.ui.common.AppCard
import com.eko.rcrm.dc.ui.common.AppTopBar
import com.eko.rcrm.dc.ui.common.ErrorBanner
import com.eko.rcrm.dc.ui.common.StatusBadge
import com.eko.rcrm.dc.ui.common.Tone
import com.eko.rcrm.dc.ui.theme.Background
import com.eko.rcrm.dc.ui.theme.MutedForeground
import com.eko.rcrm.dc.ui.theme.OnBackground
import com.eko.rcrm.dc.ui.theme.Primary
import com.eko.rcrm.dc.ui.theme.Saffron

@Composable
fun OfficialSearchScreen(
    onBack: () -> Unit,
    onCallStarted: (Int) -> Unit,
    onOpenDetail: (Int) -> Unit,
    onAddOfficial: () -> Unit,
    viewModel: OfficialSearchViewModel = hiltViewModel()
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
        topBar = {
            AppTopBar(
                title = "Call an Official",
                onBack = onBack,
                actions = {
                    IconButton(onClick = onAddOfficial) {
                        Icon(Icons.Default.PersonAdd, contentDescription = "Add official")
                    }
                }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 20.dp, vertical = 12.dp)
        ) {
            OutlinedTextField(
                value = uiState.query,
                onValueChange = viewModel::onQueryChange,
                placeholder = { Text("Search by name, phone or designation") },
                leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
                singleLine = true,
                colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Primary),
                modifier = Modifier.fillMaxWidth()
            )

            (uiState.error ?: permissionError)?.let {
                androidx.compose.foundation.layout.Spacer(modifier = Modifier.padding(top = 12.dp))
                ErrorBanner(message = it)
            }

            if (uiState.isSearching || uiState.isStartingCall) {
                androidx.compose.foundation.layout.Spacer(modifier = Modifier.padding(top = 16.dp))
                CircularProgressIndicator(color = Primary)
            }

            androidx.compose.foundation.layout.Spacer(modifier = Modifier.padding(top = 12.dp))

            LazyColumn(
                contentPadding = PaddingValues(bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                items(uiState.results, key = { it.id }) { official ->
                    OfficialRow(
                        official = official,
                        onCall = { viewModel.callOfficial(official) },
                        onOpenDetail = { onOpenDetail(official.id) }
                    )
                }
            }
        }
    }
}

@Composable
private fun OfficialRow(official: Official, onCall: () -> Unit, onOpenDetail: () -> Unit) {
    AppCard(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Column(
                modifier = Modifier
                    .weight(1f)
                    .clickable(onClick = onOpenDetail)
            ) {
                Text(text = official.name, style = MaterialTheme.typography.titleMedium)
                official.designation?.let {
                    Text(
                        text = it,
                        style = MaterialTheme.typography.bodyMedium,
                        color = OnBackground
                    )
                }
                if (official.organizationUnitName != null || official.phone != null) {
                    androidx.compose.foundation.layout.Spacer(modifier = Modifier.padding(top = 4.dp))
                }
                official.organizationUnitName?.let { unitName ->
                    Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                        Text(text = unitName, style = MaterialTheme.typography.bodySmall, color = MutedForeground)
                        official.organizationUnitType?.let { unitType ->
                            androidx.compose.foundation.layout.Spacer(modifier = Modifier.padding(start = 6.dp))
                            StatusBadge(text = unitType, tone = Tone.Primary)
                        }
                    }
                }
                official.phone?.let {
                    Text(text = it, style = MaterialTheme.typography.bodySmall, color = MutedForeground)
                }
            }
            Row {
                // Starts the call via POST /calls/outgoing; the response's channel decides
                // Knowlarity (server-side) vs this device's own SIM (native-dialer hand-off).
                Row(
                    modifier = Modifier
                        .clickable(onClick = onCall)
                        .padding(10.dp)
                ) {
                    Icon(Icons.Default.Call, contentDescription = "Call", tint = Saffron)
                }
            }
        }
    }
}
