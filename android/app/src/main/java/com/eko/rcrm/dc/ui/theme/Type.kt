package com.eko.rcrm.dc.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

// Default Material 3 type scale with an intentional weight/size hierarchy so the
// app doesn't read as flat/default-Android even without bundling custom fonts.
val RcrmTypography = Typography(
    displaySmall = Typography().displaySmall.copy(fontFamily = FontFamily.Default, fontWeight = FontWeight.Bold),
    headlineMedium = Typography().headlineMedium.copy(
        fontFamily = FontFamily.Default,
        fontWeight = FontWeight.Bold,
        fontSize = 26.sp
    ),
    headlineSmall = Typography().headlineSmall.copy(fontFamily = FontFamily.Default, fontWeight = FontWeight.Bold),
    titleLarge = Typography().titleLarge.copy(fontFamily = FontFamily.Default, fontWeight = FontWeight.SemiBold),
    titleMedium = Typography().titleMedium.copy(fontFamily = FontFamily.Default, fontWeight = FontWeight.SemiBold),
    titleSmall = Typography().titleSmall.copy(fontFamily = FontFamily.Default, fontWeight = FontWeight.Medium),
    bodyLarge = Typography().bodyLarge.copy(fontFamily = FontFamily.Default),
    bodyMedium = Typography().bodyMedium.copy(fontFamily = FontFamily.Default),
    bodySmall = Typography().bodySmall.copy(fontFamily = FontFamily.Default, color = MutedForeground),
    labelLarge = Typography().labelLarge.copy(fontFamily = FontFamily.Default, fontWeight = FontWeight.SemiBold),
    labelMedium = Typography().labelMedium.copy(fontFamily = FontFamily.Default, fontWeight = FontWeight.Medium),
    labelSmall = Typography().labelSmall.copy(fontFamily = FontFamily.Default, fontWeight = FontWeight.Medium)
)
