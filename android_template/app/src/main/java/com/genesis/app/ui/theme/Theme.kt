// GENESIS PROTECTED FILE — server-controlled theme. Colors come from ThemeConfig.kt.
package com.genesis.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.graphics.ColorUtils

/** Builds a harmonious tone from the seed hue: same hue (+shift), chosen saturation and lightness. */
private fun tone(seed: Int, lightness: Float, saturation: Float? = null, hueShift: Float = 0f): Color {
    val hsl = FloatArray(3)
    ColorUtils.colorToHSL(seed, hsl)
    val h = (hsl[0] + hueShift + 360f) % 360f
    val s = (saturation ?: hsl[1]).coerceIn(0f, 1f)
    return Color(ColorUtils.HSLToColor(floatArrayOf(h, s, lightness.coerceIn(0f, 1f))))
}

private fun seedSaturation(seed: Int): Float {
    val hsl = FloatArray(3)
    ColorUtils.colorToHSL(seed, hsl)
    return hsl[1].coerceIn(0.45f, 0.9f)
}

fun genesisLightScheme(seedArgb: Long): ColorScheme {
    val seed = seedArgb.toInt()
    val s = seedSaturation(seed)
    return lightColorScheme(
        primary = tone(seed, 0.42f, s),
        onPrimary = Color.White,
        primaryContainer = tone(seed, 0.90f, s * 0.9f),
        onPrimaryContainer = tone(seed, 0.16f, s),
        secondary = tone(seed, 0.40f, s * 0.35f, 15f),
        onSecondary = Color.White,
        secondaryContainer = tone(seed, 0.91f, s * 0.45f, 15f),
        onSecondaryContainer = tone(seed, 0.15f, s * 0.4f, 15f),
        tertiary = tone(seed, 0.42f, s * 0.8f, 35f),
        onTertiary = Color.White,
        tertiaryContainer = tone(seed, 0.90f, s * 0.7f, 35f),
        onTertiaryContainer = tone(seed, 0.16f, s * 0.8f, 35f),
        background = tone(seed, 0.985f, 0.35f),
        onBackground = tone(seed, 0.11f, 0.12f),
        surface = tone(seed, 0.985f, 0.35f),
        onSurface = tone(seed, 0.11f, 0.12f),
        surfaceVariant = tone(seed, 0.92f, 0.18f),
        onSurfaceVariant = tone(seed, 0.36f, 0.10f),
        surfaceContainerLowest = Color.White,
        surfaceContainerLow = tone(seed, 0.965f, 0.30f),
        surfaceContainer = tone(seed, 0.95f, 0.28f),
        surfaceContainerHigh = tone(seed, 0.935f, 0.24f),
        surfaceContainerHighest = tone(seed, 0.915f, 0.22f),
        outline = tone(seed, 0.62f, 0.08f),
        outlineVariant = tone(seed, 0.86f, 0.12f),
        error = Color(0xFFBA1A1A),
        errorContainer = Color(0xFFFFDAD6),
    )
}

fun genesisDarkScheme(seedArgb: Long): ColorScheme {
    val seed = seedArgb.toInt()
    val s = seedSaturation(seed)
    return darkColorScheme(
        primary = tone(seed, 0.76f, s * 0.85f),
        onPrimary = tone(seed, 0.17f, s),
        primaryContainer = tone(seed, 0.28f, s * 0.8f),
        onPrimaryContainer = tone(seed, 0.90f, s * 0.8f),
        secondary = tone(seed, 0.78f, s * 0.35f, 15f),
        onSecondary = tone(seed, 0.17f, s * 0.35f, 15f),
        secondaryContainer = tone(seed, 0.27f, s * 0.3f, 15f),
        onSecondaryContainer = tone(seed, 0.90f, s * 0.35f, 15f),
        tertiary = tone(seed, 0.76f, s * 0.7f, 35f),
        onTertiary = tone(seed, 0.17f, s * 0.7f, 35f),
        tertiaryContainer = tone(seed, 0.27f, s * 0.6f, 35f),
        onTertiaryContainer = tone(seed, 0.90f, s * 0.6f, 35f),
        background = tone(seed, 0.065f, 0.18f),
        onBackground = tone(seed, 0.92f, 0.10f),
        surface = tone(seed, 0.065f, 0.18f),
        onSurface = tone(seed, 0.92f, 0.10f),
        surfaceVariant = tone(seed, 0.22f, 0.12f),
        onSurfaceVariant = tone(seed, 0.78f, 0.10f),
        surfaceContainerLowest = tone(seed, 0.045f, 0.18f),
        surfaceContainerLow = tone(seed, 0.09f, 0.16f),
        surfaceContainer = tone(seed, 0.11f, 0.16f),
        surfaceContainerHigh = tone(seed, 0.145f, 0.14f),
        surfaceContainerHighest = tone(seed, 0.18f, 0.12f),
        outline = tone(seed, 0.55f, 0.08f),
        outlineVariant = tone(seed, 0.28f, 0.10f),
        error = Color(0xFFFFB4AB),
        errorContainer = Color(0xFF93000A),
    )
}

private val Sans = FontFamily.SansSerif

val GenesisTypography = Typography(
    displayLarge = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Bold, fontSize = 56.sp, lineHeight = 60.sp, letterSpacing = (-1.5).sp),
    displayMedium = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Bold, fontSize = 44.sp, lineHeight = 50.sp, letterSpacing = (-1).sp),
    displaySmall = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Bold, fontSize = 36.sp, lineHeight = 42.sp, letterSpacing = (-0.8).sp),
    headlineLarge = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Bold, fontSize = 32.sp, lineHeight = 38.sp, letterSpacing = (-0.6).sp),
    headlineMedium = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Bold, fontSize = 28.sp, lineHeight = 34.sp, letterSpacing = (-0.4).sp),
    headlineSmall = TextStyle(fontFamily = Sans, fontWeight = FontWeight.SemiBold, fontSize = 24.sp, lineHeight = 30.sp, letterSpacing = (-0.2).sp),
    titleLarge = TextStyle(fontFamily = Sans, fontWeight = FontWeight.SemiBold, fontSize = 21.sp, lineHeight = 27.sp, letterSpacing = (-0.1).sp),
    titleMedium = TextStyle(fontFamily = Sans, fontWeight = FontWeight.SemiBold, fontSize = 16.sp, lineHeight = 22.sp),
    titleSmall = TextStyle(fontFamily = Sans, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, lineHeight = 20.sp),
    bodyLarge = TextStyle(fontFamily = Sans, fontSize = 16.sp, lineHeight = 24.sp),
    bodyMedium = TextStyle(fontFamily = Sans, fontSize = 14.sp, lineHeight = 20.sp),
    bodySmall = TextStyle(fontFamily = Sans, fontSize = 12.sp, lineHeight = 16.sp),
    labelLarge = TextStyle(fontFamily = Sans, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, lineHeight = 20.sp, letterSpacing = 0.1.sp),
    labelMedium = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Medium, fontSize = 12.sp, lineHeight = 16.sp, letterSpacing = 0.3.sp),
    labelSmall = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Medium, fontSize = 11.sp, lineHeight = 16.sp, letterSpacing = 0.5.sp),
)

val GenesisShapes = Shapes(
    extraSmall = RoundedCornerShape(8.dp),
    small = RoundedCornerShape(12.dp),
    medium = RoundedCornerShape(20.dp),
    large = RoundedCornerShape(28.dp),
    extraLarge = RoundedCornerShape(36.dp),
)

@Composable
fun GenesisTheme(content: @Composable () -> Unit) {
    val dark = when (GENESIS_THEME_MODE) {
        "dark" -> true
        "light" -> false
        else -> isSystemInDarkTheme()
    }
    val scheme = if (dark) genesisDarkScheme(GENESIS_PRIMARY_COLOR) else genesisLightScheme(GENESIS_PRIMARY_COLOR)
    MaterialTheme(colorScheme = scheme, typography = GenesisTypography, shapes = GenesisShapes, content = content)
}
