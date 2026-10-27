package com.eko.rcrm.dc.ui.csp

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.SearchOff
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.eko.rcrm.dc.domain.model.Csp
import com.eko.rcrm.dc.nativecall.rememberNativeCallLauncher
import com.eko.rcrm.dc.ui.common.AppCard
import com.eko.rcrm.dc.ui.common.AppTopBar
import com.eko.rcrm.dc.ui.common.ErrorBanner
import com.eko.rcrm.dc.ui.common.LoadingIndicator
import com.eko.rcrm.dc.ui.common.SearchField
import com.eko.rcrm.dc.ui.common.StatusBadge
import com.eko.rcrm.dc.ui.common.Tone
import com.eko.rcrm.dc.ui.theme.Background
import com.eko.rcrm.dc.ui.theme.MutedForeground
import com.eko.rcrm.dc.ui.theme.Primary

@Composable
fun CspListScreen(
    onBack: () -> Unit,
    onCallStarted: (Int) -> Unit,
    onOpenBrief: (Int) -> Unit,
    viewModel: CspListViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()

    // Place CSP calls through the app's own outbound flow (NativeCallForegroundService), which
    // reliably captures the number and records both sides - a plain ACTION_DIAL would often lose
    // the number on an outgoing call and record nothing.
    val launchNativeCall = rememberNativeCallLauncher(onPermissionDenied = {})
    LaunchedEffect(Unit) {
        viewModel.launchNativeCall.collect { request -> launchNativeCall(request) }
    }
    LaunchedEffect(Unit) {
        viewModel.navigateToReview.collect { callSessionId -> onCallStarted(callSessionId) }
    }

    Scaffold(
        containerColor = Background,
        topBar = { AppTopBar(title = "My CSPs", onBack = onBack) }
    ) { padding ->
        Column(modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 20.dp)) {
            when {
                uiState.isLoading && uiState.items.isEmpty() -> LoadingIndicator()
                uiState.error != null && uiState.items.isEmpty() ->
                    ErrorBanner(message = uiState.error!!, modifier = Modifier.padding(top = 16.dp))
                uiState.items.isEmpty() -> Box(Modifier.fillMaxSize(), Alignment.Center) {
                    Text(
                        text = "No CSPs assigned to you yet.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MutedForeground
                    )
                }
                else -> {
                    val visible = uiState.visibleItems
                    Spacer(modifier = Modifier.height(12.dp))
                    SearchField(
                        value = uiState.query,
                        onValueChange = viewModel::onQueryChange,
                        placeholder = "Search name, code, number or branch"
                    )
                    Spacer(modifier = Modifier.height(10.dp))
                    Text(
                        text = if (uiState.query.isBlank())
                            "${uiState.items.size} CSP${if (uiState.items.size == 1) "" else "s"} assigned to you"
                        else "${visible.size} of ${uiState.items.size} match",
                        style = MaterialTheme.typography.bodySmall,
                        color = MutedForeground,
                        modifier = Modifier.padding(bottom = 6.dp)
                    )

                    if (visible.isEmpty()) {
                        Box(Modifier.fillMaxSize(), Alignment.Center) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Icon(
                                    Icons.Default.SearchOff,
                                    contentDescription = null,
                                    tint = MutedForeground,
                                    modifier = Modifier.size(40.dp)
                                )
                                Spacer(Modifier.height(8.dp))
                                Text(
                                    "No CSP matches \"${uiState.query}\"",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = MutedForeground
                                )
                            }
                        }
                    } else {
                        LazyColumn(
                            contentPadding = PaddingValues(top = 4.dp, bottom = 20.dp),
                            verticalArrangement = Arrangement.spacedBy(10.dp),
                            modifier = Modifier.animateContentSize()
                        ) {
                            items(visible, key = { it.id }) { csp ->
                                CspRow(csp = csp, onDial = viewModel::call, onOpenBrief = onOpenBrief)
                            }
                        }
                    }
                }
            }
        }
    }
}

private val AvatarColors = listOf(
    Color(0xFF0092CC), Color(0xFF1F6548), Color(0xFF854F0B),
    Color(0xFF993556), Color(0xFF5B4BA8), Color(0xFF00796B)
)

private fun initials(name: String): String =
    name.trim().split(" ").filter { it.isNotBlank() }.take(2)
        .joinToString("") { it.first().uppercase() }.ifBlank { "?" }

@Composable
private fun CspRow(csp: Csp, onDial: (String) -> Unit, onOpenBrief: (Int) -> Unit) {
    // Tapping the card opens the pre-call briefing; the call buttons inside still dial straight away.
    AppCard(modifier = Modifier.fillMaxWidth(), onClick = { onOpenBrief(csp.id) }) {
        Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                val color = AvatarColors[(csp.name.hashCode() and 0x7fffffff) % AvatarColors.size]
                Box(
                    modifier = Modifier.size(40.dp).background(color.copy(alpha = 0.14f), CircleShape),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = initials(csp.name),
                        color = color,
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.Bold
                    )
                }
                Spacer(Modifier.size(12.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = csp.name,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    val sub = listOfNotNull(csp.branchName, csp.district).joinToString(" · ")
                    if (sub.isNotBlank()) {
                        Text(
                            text = sub,
                            style = MaterialTheme.typography.bodySmall,
                            color = MutedForeground,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                }
                csp.category?.takeIf { it.isNotBlank() }?.let {
                    StatusBadge(text = it, tone = Tone.Neutral)
                }
            }

            csp.mobile?.takeIf { it.isNotBlank() }?.let { number ->
                NumberRow(label = "Primary", number = number, onDial = onDial)
            }
            csp.alternateMobile?.takeIf { it.isNotBlank() && it != csp.mobile }?.let { number ->
                NumberRow(label = "Alternate", number = number, onDial = onDial)
            }
            Text(
                text = "Tap for briefing before you call",
                style = MaterialTheme.typography.labelSmall,
                color = Primary,
                modifier = Modifier.padding(top = 10.dp)
            )
            if (csp.mobile.isNullOrBlank() && csp.alternateMobile.isNullOrBlank()) {
                Text(
                    text = "No number on record",
                    style = MaterialTheme.typography.bodySmall,
                    color = MutedForeground,
                    modifier = Modifier.padding(top = 6.dp)
                )
            }
        }
    }
}

@Composable
private fun NumberRow(label: String, number: String, onDial: (String) -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Column {
            Text(text = label, style = MaterialTheme.typography.labelSmall, color = MutedForeground)
            Text(text = number, style = MaterialTheme.typography.bodyMedium, color = Primary)
        }
        androidx.compose.material3.FilledIconButton(
            onClick = { onDial(number) },
            colors = androidx.compose.material3.IconButtonDefaults.filledIconButtonColors(
                containerColor = Primary, contentColor = Color.White
            )
        ) {
            Icon(Icons.Default.Call, contentDescription = "Call $number")
        }
    }
}
