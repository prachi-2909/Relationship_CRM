package com.eko.rcrm.dc.ui.common

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.ErrorOutline
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.eko.rcrm.dc.ui.theme.Accent
import com.eko.rcrm.dc.ui.theme.Destructive
import com.eko.rcrm.dc.ui.theme.MutedForeground
import com.eko.rcrm.dc.ui.theme.Primary
import com.eko.rcrm.dc.ui.theme.Saffron

@Composable
fun LoadingIndicator(modifier: Modifier = Modifier) {
    Box(modifier = modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
        CircularProgressIndicator(color = Primary)
    }
}

@Composable
fun ErrorBanner(message: String, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .background(Destructive.copy(alpha = 0.1f), RoundedCornerShape(12.dp))
            .padding(12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(Icons.Default.ErrorOutline, contentDescription = null, tint = Destructive, modifier = Modifier.size(20.dp))
        androidx.compose.foundation.layout.Spacer(modifier = Modifier.size(8.dp))
        Text(text = message, color = Destructive, style = MaterialTheme.typography.bodyMedium)
    }
}

enum class Tone { Neutral, Primary, Good, Warn, Danger }

private fun Tone.color(): Color = when (this) {
    Tone.Neutral -> MutedForeground
    Tone.Primary -> Primary
    Tone.Good -> Accent
    Tone.Warn -> Saffron
    Tone.Danger -> Destructive
}

/** Mirrors the web app's status tone system for processing_status / identity_status. */
@Composable
fun StatusBadge(text: String, tone: Tone, modifier: Modifier = Modifier) {
    val color = tone.color()
    Box(
        modifier = modifier
            .background(color.copy(alpha = 0.12f), RoundedCornerShape(999.dp))
            .padding(horizontal = 10.dp, vertical = 4.dp)
    ) {
        Text(
            text = text,
            color = color,
            style = MaterialTheme.typography.labelMedium
        )
    }
}

fun processingStatusTone(status: String?): Tone = when (status) {
    "initiated", "ringing", "connected", "ended", "uploaded", "transcribing", "analyzing", "upload_pending" -> Tone.Neutral
    "recording", "review_required" -> Tone.Primary
    "approved", "crm_logged" -> Tone.Good
    "no_recording", "recording_unavailable", "upload_failed", "transcription_failed",
    "analysis_failed", "review_rejected", "crm_write_failed", "cancelled" -> Tone.Danger
    else -> Tone.Neutral
}

fun identityStatusTone(status: String?): Tone = when (status) {
    "registered", "verified_new_official" -> Tone.Good
    "unregistered" -> Tone.Warn
    "possible_identity" -> Tone.Primary
    "unidentified" -> Tone.Neutral
    else -> Tone.Neutral
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AppTopBar(
    title: String,
    onBack: (() -> Unit)? = null
) {
    TopAppBar(
        title = { Text(text = title, style = MaterialTheme.typography.titleLarge) },
        navigationIcon = {
            if (onBack != null) {
                IconButton(onClick = onBack) {
                    Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                }
            }
        },
        colors = TopAppBarDefaults.topAppBarColors(
            containerColor = MaterialTheme.colorScheme.background,
            titleContentColor = MaterialTheme.colorScheme.onBackground
        )
    )
}

/** Saffron-branded call-to-action button, used for "Call" and "Confirm & Log" actions. */
@Composable
fun CtaButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier,
        shape = RoundedCornerShape(16.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = Saffron,
            contentColor = Color.White,
            disabledContainerColor = Saffron.copy(alpha = 0.4f),
            disabledContentColor = Color.White.copy(alpha = 0.7f)
        ),
        contentPadding = PaddingValues(horizontal = 24.dp, vertical = 14.dp)
    ) {
        Text(text = text, style = MaterialTheme.typography.labelLarge)
    }
}
