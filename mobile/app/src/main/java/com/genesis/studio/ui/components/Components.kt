package com.genesis.studio.ui.components

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsFocusedAsState
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.addPathNodes
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.genesis.studio.ui.theme.Ui

fun parseHex(hex: String?, fallback: Color = Ui.Accent): Color = try {
    if (hex == null) fallback else Color(android.graphics.Color.parseColor(hex))
} catch (e: IllegalArgumentException) {
    fallback
}

/** The Genesis mark: a soft four-point star. */
@Composable
fun AppMark(size: Dp, modifier: Modifier = Modifier, color: Color = Ui.Accent) {
    Canvas(modifier.size(size)) {
        val s = this.size.minDimension
        val c = s / 2f
        val k = s * 0.08f
        val p = Path().apply {
            moveTo(c, 0f)
            cubicTo(c + k, c - k, c + k, c - k, s, c)
            cubicTo(c + k, c + k, c + k, c + k, c, s)
            cubicTo(c - k, c + k, c - k, c + k, 0f, c)
            cubicTo(c - k, c - k, c - k, c - k, c, 0f)
            close()
        }
        drawPath(p, color)
    }
}

/** White rounded card with a hairline border. */
@Composable
fun SoftCard(
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
    background: Color = Ui.Card,
    padding: Dp = 20.dp,
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(
        modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(24.dp))
            .background(background)
            .border(1.dp, if (background == Ui.Card) Ui.Line else Color.Transparent, RoundedCornerShape(24.dp))
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
            .padding(padding),
        content = content,
    )
}

/** The one main action on a screen. */
@Composable
fun BigButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    loading: Boolean = false,
    icon: ImageVector? = null,
    color: Color = Ui.Accent,
) {
    val source = remember { MutableInteractionSource() }
    val pressed by source.collectIsPressedAsState()
    val active = enabled && !loading
    Row(
        modifier
            .fillMaxWidth()
            .height(60.dp)
            .scale(if (pressed) 0.98f else 1f)
            .clip(CircleShape)
            .background(if (active || loading) color else Ui.Soft)
            .clickable(enabled = active, interactionSource = source, indication = null, onClick = onClick),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center,
    ) {
        if (loading) {
            CircularProgressIndicator(Modifier.size(20.dp), color = Color.White, strokeWidth = 2.5.dp)
            Box(Modifier.size(12.dp))
        } else if (icon != null) {
            Icon(icon, null, tint = if (active) Color.White else Ui.Text3, modifier = Modifier.size(22.dp))
            Box(Modifier.size(10.dp))
        }
        Text(text, style = MaterialTheme.typography.labelLarge, color = if (active || loading) Color.White else Ui.Text3)
    }
}

/** A secondary action: soft grey pill. */
@Composable
fun QuietButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    icon: ImageVector? = null,
    enabled: Boolean = true,
    textColor: Color = Ui.Text,
) {
    Row(
        modifier
            .fillMaxWidth()
            .height(56.dp)
            .clip(CircleShape)
            .background(Ui.Soft)
            .clickable(enabled = enabled, onClick = onClick),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center,
    ) {
        if (icon != null) {
            Icon(icon, null, tint = if (enabled) textColor else Ui.Text3, modifier = Modifier.size(20.dp))
            Box(Modifier.size(8.dp))
        }
        Text(text, style = MaterialTheme.typography.labelLarge, color = if (enabled) textColor else Ui.Text3)
    }
}

/** Round icon button used for back / settings. */
@Composable
fun CircleIconButton(icon: ImageVector, contentDescription: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    Box(
        modifier.size(46.dp).clip(CircleShape).background(Ui.Card).border(1.dp, Ui.Line, CircleShape).clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) { Icon(icon, contentDescription, tint = Ui.Text, modifier = Modifier.size(22.dp)) }
}

/** Text box with a clear focus ring. */
@Composable
fun InputBox(
    value: String,
    onValueChange: (String) -> Unit,
    placeholder: String,
    modifier: Modifier = Modifier,
    label: String? = null,
    singleLine: Boolean = true,
    minHeight: Dp = 58.dp,
    textStyle: TextStyle = MaterialTheme.typography.bodyLarge,
    keyboardOptions: KeyboardOptions = KeyboardOptions.Default,
    bottomSpace: Dp = 0.dp,
) {
    val source = remember { MutableInteractionSource() }
    val focused by source.collectIsFocusedAsState()
    Column(modifier) {
        if (label != null) {
            Text(label, style = MaterialTheme.typography.labelMedium, color = Ui.Text2, modifier = Modifier.padding(start = 6.dp, bottom = 8.dp))
        }
        BasicTextField(
            value = value,
            onValueChange = onValueChange,
            singleLine = singleLine,
            textStyle = textStyle.copy(color = Ui.Text),
            cursorBrush = SolidColor(Ui.Accent),
            interactionSource = source,
            keyboardOptions = keyboardOptions,
            modifier = Modifier.fillMaxWidth(),
            decorationBox = { inner ->
                Box(
                    Modifier
                        .fillMaxWidth()
                        .heightIn(min = minHeight)
                        .clip(RoundedCornerShape(20.dp))
                        .background(Ui.Card)
                        .border(BorderStroke(if (focused) 2.dp else 1.dp, if (focused) Ui.Accent else Ui.Line), RoundedCornerShape(20.dp))
                        .padding(start = 18.dp, end = 18.dp, top = 16.dp, bottom = 16.dp + bottomSpace),
                    contentAlignment = if (singleLine) Alignment.CenterStart else Alignment.TopStart,
                ) {
                    if (value.isEmpty()) Text(placeholder, style = textStyle, color = Ui.Text3)
                    inner()
                }
            },
        )
    }
}

/** A made app's icon: its own color and first letter. Gently pulses while it's being made. */
@Composable
fun AppIcon(name: String?, colorHex: String?, size: Dp, modifier: Modifier = Modifier, busy: Boolean = false) {
    val base = parseHex(colorHex)
    val pulse = if (busy) {
        rememberInfiniteTransition(label = "icon").animateFloat(0.55f, 1f, infiniteRepeatable(tween(900), RepeatMode.Reverse), label = "a").value
    } else 1f
    Box(
        modifier
            .size(size)
            .alpha(pulse)
            .clip(RoundedCornerShape(size * 0.3f))
            .background(Brush.linearGradient(listOf(lerp(base, Color.White, 0.15f), base))),
        contentAlignment = Alignment.Center,
    ) {
        if (name.isNullOrBlank()) {
            AppMark(size * 0.42f, color = Color.White)
        } else {
            Text(
                name.trim().first().uppercase(),
                color = Color.White,
                fontWeight = FontWeight.Bold,
                fontSize = (size.value * 0.42f).sp,
                textAlign = TextAlign.Center,
            )
        }
    }
}

enum class Simple(val label: String) { Making("Making…"), Ready("Ready"), Failed("Didn't work") }

fun simpleStatus(status: String): Simple = when (status) {
    "succeeded" -> Simple.Ready
    "failed" -> Simple.Failed
    else -> Simple.Making
}

/** Plain-language status pill. */
@Composable
fun StatusPill(status: String, modifier: Modifier = Modifier) {
    val s = simpleStatus(status)
    val (fg, bg) = when (s) {
        Simple.Ready -> Ui.Green to Ui.GreenSoft
        Simple.Failed -> Ui.Red to Ui.RedSoft
        Simple.Making -> Ui.Accent to Ui.AccentSoft
    }
    Text(
        s.label,
        style = MaterialTheme.typography.labelSmall,
        color = fg,
        modifier = modifier.clip(CircleShape).background(bg).padding(horizontal = 10.dp, vertical = 4.dp),
    )
}

/** Friendly one-liner for what's happening right now. */
fun friendlyStage(stage: String): String = when (stage) {
    "generating" -> "Designing your app"
    "validating" -> "Checking everything is safe"
    "building" -> "Building your app"
    "repairing" -> "Fixing a few things"
    "verifying" -> "Almost ready"
    "succeeded" -> "Your app is ready"
    "failed" -> "This one didn't work"
    else -> "Getting started"
}

/** Suggestion chip with an emoji. */
@Composable
fun Suggestion(emoji: String, text: String, onClick: () -> Unit) {
    Row(
        Modifier
            .clip(CircleShape)
            .background(Ui.Card)
            .border(1.dp, Ui.Line, CircleShape)
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(emoji, fontSize = 16.sp)
        Box(Modifier.size(8.dp))
        Text(text, style = MaterialTheme.typography.labelMedium, color = Ui.Text)
    }
}

@Composable
fun SimpleProgress(progress: Float, modifier: Modifier = Modifier, color: Color = Ui.Accent) {
    val p by animateFloatAsState(progress.coerceIn(0.04f, 1f), tween(700), label = "progress")
    Box(modifier.fillMaxWidth().height(8.dp).clip(CircleShape).background(Ui.Soft)) {
        Box(Modifier.fillMaxWidth(p).height(8.dp).clip(CircleShape).background(color))
    }
}

@Composable
fun SectionTitle(text: String, modifier: Modifier = Modifier) {
    Text(text, style = MaterialTheme.typography.titleLarge, color = Ui.Text, modifier = modifier)
}

/** Material "mic" glyph (core icons don't include it). */
val MicIcon: ImageVector by lazy {
    ImageVector.Builder("Mic", 24.dp, 24.dp, 24f, 24f)
        .addPath(
            addPathNodes(
                "M12,14c1.66,0 3,-1.34 3,-3V5c0,-1.66 -1.34,-3 -3,-3S9,3.34 9,5v6c0,1.66 1.34,3 3,3z" +
                    "M17.3,11c0,3 -2.54,5.1 -5.3,5.1S6.7,14 6.7,11H5c0,3.41 2.72,6.23 6,6.72V21h2v-3.28c3.28,-0.48 6,-3.3 6,-6.72h-1.7z",
            ),
            fill = SolidColor(Color.Black),
        )
        .build()
}

/** Pill button: microphone + "Speak". */
@Composable
fun SpeakButton(onClick: () -> Unit, modifier: Modifier = Modifier) {
    Row(
        modifier
            .clip(CircleShape)
            .background(Ui.AccentSoft)
            .clickable(onClick = onClick)
            .padding(start = 12.dp, end = 16.dp, top = 9.dp, bottom = 9.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(MicIcon, contentDescription = "Speak your idea", tint = Ui.Accent, modifier = Modifier.size(20.dp))
        Box(Modifier.size(6.dp))
        Text("Speak", style = MaterialTheme.typography.labelMedium, color = Ui.Accent)
    }
}
