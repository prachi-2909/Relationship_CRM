package com.eko.rcrm.dc.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

// The web app is a light, warm-ivory branded surface with no dark mode counterpart yet,
// so this app intentionally always renders the light scheme regardless of system theme -
// mirrors the web CRM 1:1 rather than guessing at an unspecified dark palette.
private val RcrmLightColorScheme = lightColorScheme(
    primary = Primary,
    onPrimary = OnPrimary,
    secondary = Secondary,
    onSecondary = OnPrimary,
    background = Background,
    onBackground = OnBackground,
    surface = Surface,
    onSurface = OnBackground,
    surfaceVariant = Muted,
    onSurfaceVariant = MutedForeground,
    error = Destructive,
    onError = OnPrimary,
    outline = Border,
    tertiary = Accent,
    onTertiary = OnPrimary
)

@Composable
fun RcrmTheme(content: @Composable () -> Unit) {
    val colorScheme = RcrmLightColorScheme
    val view = LocalView.current
    if (!view.isInEditMode) {
        val activity = view.context as? android.app.Activity
        activity?.window?.let { window ->
            window.statusBarColor = Background.toArgb()
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = true
        }
    }
    MaterialTheme(
        colorScheme = colorScheme,
        typography = RcrmTypography,
        content = content
    )
}
