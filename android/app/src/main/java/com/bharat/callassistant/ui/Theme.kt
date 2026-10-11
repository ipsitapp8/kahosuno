package com.bharat.callassistant.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// High-contrast palette: near-black text on white, saturated colours for actions.
val Navy = Color(0xFF0B3D91)
val AlertRed = Color(0xFFC62828)
val AlertYellow = Color(0xFFFFD600)
val GoodGreen = Color(0xFF1B5E20)

private val Colors = lightColorScheme(
    primary = Navy,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFD6E3FF),
    onPrimaryContainer = Color(0xFF001A41),
    secondary = Color(0xFF3C4A66),
    background = Color.White,
    onBackground = Color(0xFF101010),
    surface = Color.White,
    onSurface = Color(0xFF101010),
    surfaceVariant = Color(0xFFEDEFF4),
    onSurfaceVariant = Color(0xFF2B2F38),
    error = Color(0xFFB00020),
    onError = Color.White,
    outline = Color(0xFF55596A),
)

// Bigger than Material defaults: this app is for elderly users.
private val AppTypography = Typography(
    headlineMedium = TextStyle(fontSize = 30.sp, lineHeight = 38.sp, fontWeight = FontWeight.Bold),
    headlineSmall = TextStyle(fontSize = 26.sp, lineHeight = 34.sp, fontWeight = FontWeight.Bold),
    titleLarge = TextStyle(fontSize = 24.sp, lineHeight = 30.sp, fontWeight = FontWeight.Bold),
    titleMedium = TextStyle(fontSize = 20.sp, lineHeight = 26.sp, fontWeight = FontWeight.SemiBold),
    bodyLarge = TextStyle(fontSize = 20.sp, lineHeight = 28.sp),
    bodyMedium = TextStyle(fontSize = 18.sp, lineHeight = 24.sp),
    bodySmall = TextStyle(fontSize = 15.sp, lineHeight = 20.sp),
    labelLarge = TextStyle(fontSize = 18.sp, lineHeight = 24.sp, fontWeight = FontWeight.SemiBold),
    labelMedium = TextStyle(fontSize = 16.sp, lineHeight = 20.sp),
)

/** Smallest size for anything tappable (Android guidance is 48dp; we go bigger). */
val TouchTarget = 56.dp
val BigButton = 68.dp

/**
 * [fontScale] comes from Settings and multiplies the system font size, so someone who
 * needs very large text can make it bigger than the phone's own setting allows.
 */
@Composable
fun BharatTheme(fontScale: Float = 1f, content: @Composable () -> Unit) {
    val density = LocalDensity.current
    CompositionLocalProvider(
        LocalDensity provides Density(density.density, density.fontScale * fontScale),
    ) {
        MaterialTheme(colorScheme = Colors, typography = AppTypography, content = content)
    }
}
