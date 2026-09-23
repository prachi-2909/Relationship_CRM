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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.eko.rcrm.dc.domain.model.Official
import com.eko.rcrm.dc.ui.common.AppTopBar
import com.eko.rcrm.dc.ui.common.ErrorBanner
import com.eko.rcrm.dc.ui.theme.Background
import com.eko.rcrm.dc.ui.theme.MutedForeground
import com.eko.rcrm.dc.ui.theme.Primary
import com.eko.rcrm.dc.ui.theme.Saffron
import com.eko.rcrm.dc.ui.theme.Surface

@Composable
fun OfficialSearchScreen(
    onBack: () -> Unit,
    onCallStarted: (Int) -> Unit,
    viewModel: OfficialSearchViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()

    LaunchedEffect(Unit) {
        viewModel.navigateToReview.collect { callSessionId -> onCallStarted(callSessionId) }
    }

    Scaffold(
        containerColor = Background,
        topBar = { AppTopBar(title = "Call an Official", onBack = onBack) }
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

            uiState.error?.let {
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
                        onCall = { viewModel.callOfficial(official) }
                    )
                }
            }
        }
    }
}

@Composable
private fun OfficialRow(official: Official, onCall: () -> Unit) {
    Card(
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = Surface),
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(text = official.name, style = MaterialTheme.typography.titleMedium)
                val subtitle = listOfNotNull(official.designation, official.location).joinToString(" • ")
                if (subtitle.isNotBlank()) {
                    Text(text = subtitle, style = MaterialTheme.typography.bodySmall, color = MutedForeground)
                }
                official.phone?.let {
                    Text(text = it, style = MaterialTheme.typography.bodySmall, color = MutedForeground)
                }
            }
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
