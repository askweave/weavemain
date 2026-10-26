package com.genesis.studio.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/** Calm, simple palette: warm off-white, white cards, one friendly accent. */
object Ui {
    val Bg = Color(0xFFF7F6F3)
    val Card = Color(0xFFFFFFFF)
    val Soft = Color(0xFFEFEEEA)
    val Line = Color(0xFFE6E4DF)

    val Text = Color(0xFF17171C)
    val Text2 = Color(0xFF66666F)
    val Text3 = Color(0xFFA3A3AB)

    val Accent = Color(0xFF5B4CF0)
    val AccentSoft = Color(0xFFEDEBFF)
    val Green = Color(0xFF15A05A)
    val GreenSoft = Color(0xFFE6F6EC)
    val Red = Color(0xFFD9363E)
    val RedSoft = Color(0xFFFDECEC)
    val Amber = Color(0xFFB7791F)
}

private val Sans = FontFamily.SansSerif

val GenesisTypography = Typography(
    displaySmall = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Bold, fontSize = 32.sp, lineHeight = 38.sp, letterSpacing = (-0.8).sp),
    headlineSmall = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Bold, fontSize = 24.sp, lineHeight = 30.sp, letterSpacing = (-0.4).sp),
    titleLarge = TextStyle(fontFamily = Sans, fontWeight = FontWeight.SemiBold, fontSize = 20.sp, lineHeight = 26.sp, letterSpacing = (-0.2).sp),
    titleMedium = TextStyle(fontFamily = Sans, fontWeight = FontWeight.SemiBold, fontSize = 17.sp, lineHeight = 22.sp),
    bodyLarge = TextStyle(fontFamily = Sans, fontSize = 17.sp, lineHeight = 25.sp),
    bodyMedium = TextStyle(fontFamily = Sans, fontSize = 15.sp, lineHeight = 22.sp),
    bodySmall = TextStyle(fontFamily = Sans, fontSize = 13.sp, lineHeight = 18.sp),
    labelLarge = TextStyle(fontFamily = Sans, fontWeight = FontWeight.SemiBold, fontSize = 17.sp, lineHeight = 22.sp),
    labelMedium = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Medium, fontSize = 14.sp, lineHeight = 18.sp),
    labelSmall = TextStyle(fontFamily = Sans, fontWeight = FontWeight.SemiBold, fontSize = 12.sp, lineHeight = 16.sp, letterSpacing = 0.2.sp),
)

val Mono = TextStyle(fontFamily = FontFamily.Monospace, fontSize = 11.sp, lineHeight = 16.sp, color = Ui.Text2)

@Composable
fun GenesisTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = Ui.Accent,
            onPrimary = Color.White,
            primaryContainer = Ui.AccentSoft,
            background = Ui.Bg,
            onBackground = Ui.Text,
            surface = Ui.Card,
            onSurface = Ui.Text,
            surfaceVariant = Ui.Soft,
            onSurfaceVariant = Ui.Text2,
            surfaceContainer = Ui.Soft,
            outline = Ui.Line,
            outlineVariant = Ui.Line,
            error = Ui.Red,
        ),
        typography = GenesisTypography,
        content = content,
    )
}
