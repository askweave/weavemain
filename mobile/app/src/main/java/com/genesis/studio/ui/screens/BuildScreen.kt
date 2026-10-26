package com.genesis.studio.ui.screens

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.genesis.studio.AppViewModel
import com.genesis.studio.DownloadState
import com.genesis.studio.data.ApiException
import com.genesis.studio.data.Build
import com.genesis.studio.ui.components.AppIcon
import com.genesis.studio.ui.components.BigButton
import com.genesis.studio.ui.components.CircleIconButton
import com.genesis.studio.ui.components.QuietButton
import com.genesis.studio.ui.components.SimpleProgress
import com.genesis.studio.ui.components.SoftCard
import com.genesis.studio.ui.components.friendlyStage
import com.genesis.studio.ui.theme.Mono
import com.genesis.studio.ui.theme.Ui
import kotlinx.coroutines.delay

@Composable
fun BuildScreen(vm: AppViewModel, buildId: String, onBack: () -> Unit, onOpenBuild: (String) -> Unit) {
    BackHandler(onBack = onBack)
    var build by remember(buildId) { mutableStateOf(vm.builds.firstOrNull { it.id == buildId }) }
    var log by remember(buildId) { mutableStateOf("") }
    var detailsOpen by rememberSaveable { mutableStateOf(false) }
    var loadError by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(buildId, detailsOpen) {
        while (true) {
            try {
                val b = vm.fetchBuild(buildId)
                build = b
                loadError = null
                if (detailsOpen) log = vm.fetchLog(buildId)
                if (b == null || b.isDone) break
            } catch (e: ApiException) {
                loadError = e.message
            }
            delay(1500)
        }
    }

    Column(Modifier.fillMaxSize().background(Ui.Bg).statusBarsPadding().navigationBarsPadding()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 8.dp)) {
            CircleIconButton(Icons.AutoMirrored.Filled.ArrowBack, "Back", onBack)
        }
        val b = build
        if (b == null) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Text(loadError ?: "Loading…", color = Ui.Text2) }
            return@Column
        }
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 22.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Spacer(Modifier.height(12.dp))
            AppIcon(b.appName, b.primaryColor, 104.dp, busy = !b.isDone)
            Spacer(Modifier.height(20.dp))
            Text(
                b.appName ?: "Making your app…",
                style = MaterialTheme.typography.headlineSmall,
                color = Ui.Text,
                textAlign = TextAlign.Center,
            )
            b.description?.let {
                Spacer(Modifier.height(8.dp))
                Text(it, style = MaterialTheme.typography.bodyMedium, color = Ui.Text2, textAlign = TextAlign.Center)
            }
            Spacer(Modifier.height(28.dp))

            when (b.status) {
                "succeeded" -> ReadyCard(vm, b)
                "failed" -> FailedCard(vm, b, onOpenBuild)
                else -> MakingCard(b)
            }
            loadError?.let {
                Spacer(Modifier.height(10.dp))
                Text(it, style = MaterialTheme.typography.bodySmall, color = Ui.Amber, textAlign = TextAlign.Center)
            }

            if (b.features.isNotEmpty()) {
                Spacer(Modifier.height(16.dp))
                SoftCard {
                    Text("What it can do", style = MaterialTheme.typography.titleMedium, color = Ui.Text)
                    Spacer(Modifier.height(12.dp))
                    b.features.forEach { f ->
                        Row(Modifier.padding(vertical = 5.dp)) {
                            Box(
                                Modifier.size(22.dp).clip(CircleShape).background(Ui.AccentSoft),
                                contentAlignment = Alignment.Center,
                            ) { Icon(Icons.Filled.Check, null, tint = Ui.Accent, modifier = Modifier.size(14.dp)) }
                            Spacer(Modifier.width(12.dp))
                            Text(f, style = MaterialTheme.typography.bodyMedium, color = Ui.Text)
                        }
                    }
                }
            }

            Spacer(Modifier.height(16.dp))
            Details(b, log, detailsOpen) { detailsOpen = !detailsOpen }
            Spacer(Modifier.height(32.dp))
        }
    }
}

@Composable
private fun MakingCard(b: Build) {
    SoftCard {
        Text(friendlyStage(b.stage), style = MaterialTheme.typography.titleLarge, color = Ui.Text)
        Spacer(Modifier.height(16.dp))
        SimpleProgress(b.progress / 100f)
        Spacer(Modifier.height(20.dp))
        val step = when (b.stage) {
            "queued", "generating", "validating" -> 0
            else -> 1
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            listOf("Design", "Build", "Ready").forEachIndexed { i, label ->
                StepDot(label, done = i < step, active = i == step)
            }
        }
        Spacer(Modifier.height(18.dp))
        Text(
            "This usually takes 1–3 minutes. You can leave this screen — your app will be in “Your apps”.",
            style = MaterialTheme.typography.bodySmall,
            color = Ui.Text2,
        )
    }
}

@Composable
private fun StepDot(label: String, done: Boolean, active: Boolean) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            Modifier.size(24.dp).clip(CircleShape).background(
                when {
                    done -> Ui.Accent
                    active -> Ui.AccentSoft
                    else -> Ui.Soft
                },
            ),
            contentAlignment = Alignment.Center,
        ) {
            when {
                done -> Icon(Icons.Filled.Check, null, tint = Color.White, modifier = Modifier.size(14.dp))
                active -> Box(Modifier.size(8.dp).clip(CircleShape).background(Ui.Accent))
            }
        }
        Spacer(Modifier.width(8.dp))
        Text(label, style = MaterialTheme.typography.labelMedium, color = if (done || active) Ui.Text else Ui.Text3)
    }
}

@Composable
private fun ReadyCard(vm: AppViewModel, b: Build) {
    val context = LocalContext.current
    val dl = vm.downloads[b.id] ?: DownloadState.Idle
    val downloading = dl as? DownloadState.Downloading
    Column(Modifier.fillMaxWidth()) {
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(Ui.GreenSoft).padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(Modifier.size(28.dp).clip(CircleShape).background(Ui.Green), contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.Check, null, tint = Color.White, modifier = Modifier.size(18.dp))
            }
            Spacer(Modifier.width(12.dp))
            Text("Your app is ready", style = MaterialTheme.typography.titleMedium, color = Ui.Green)
        }
        Spacer(Modifier.height(16.dp))
        BigButton(
            text = if (downloading != null) "Downloading ${(downloading.progress * 100).toInt()}%" else "Install",
            onClick = { vm.install(b, context) },
            loading = downloading != null,
            icon = Icons.Filled.PlayArrow,
        )
        Spacer(Modifier.height(10.dp))
        QuietButton("Share", onClick = { vm.share(b, context) }, icon = Icons.Filled.Share, enabled = downloading == null)
        (dl as? DownloadState.Failed)?.let {
            Spacer(Modifier.height(10.dp))
            Text(it.message, style = MaterialTheme.typography.bodySmall, color = Ui.Red)
        }
        Spacer(Modifier.height(12.dp))
        Text(
            vm.notice ?: "Your phone will ask you to confirm before installing.",
            style = MaterialTheme.typography.bodySmall,
            color = if (vm.notice != null) Ui.Amber else Ui.Text2,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Composable
private fun FailedCard(vm: AppViewModel, b: Build, onOpenBuild: (String) -> Unit) {
    SoftCard(background = Ui.RedSoft) {
        Text("This one didn't work", style = MaterialTheme.typography.titleLarge, color = Ui.Red)
        Spacer(Modifier.height(6.dp))
        Text(
            "It happens sometimes. Try again, or describe your app a little differently.",
            style = MaterialTheme.typography.bodyMedium,
            color = Ui.Text,
        )
        Spacer(Modifier.height(16.dp))
        BigButton(
            text = if (vm.creating) "Starting…" else "Try again",
            onClick = { vm.create(b.prompt, null, onOpenBuild) },
            loading = vm.creating,
            icon = Icons.Filled.Refresh,
        )
    }
}

@Composable
private fun Details(b: Build, log: String, open: Boolean, onToggle: () -> Unit) {
    val rotation by animateFloatAsState(if (open) 180f else 0f, label = "chevron")
    SoftCard(padding = 0.dp) {
        Row(
            Modifier.fillMaxWidth().clickable(onClick = onToggle).padding(20.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("Details", style = MaterialTheme.typography.titleMedium, color = Ui.Text2, modifier = Modifier.weight(1f))
            Icon(Icons.Filled.KeyboardArrowDown, null, tint = Ui.Text3, modifier = Modifier.rotate(rotation))
        }
        AnimatedVisibility(open) {
            Column(Modifier.padding(start = 20.dp, end = 20.dp, bottom = 20.dp)) {
                DetailLine("You asked for", b.prompt)
                b.packageId?.let { DetailLine("App ID", it) }
                b.apk?.let { DetailLine("Size", "%.1f MB".format(it.size / 1_048_576.0)) }
                if (b.attempts.isNotEmpty()) {
                    DetailLine("Build attempts", b.attempts.joinToString("\n") { a ->
                        "#${a.n}: " + if (a.passed) "worked (${a.seconds.toInt()}s)" else "${a.errors.size} problem(s)" +
                            (a.patchExplanation?.let { " → fixed: $it" } ?: "")
                    })
                }
                b.apk?.checks?.takeIf { it.isNotEmpty() }?.let { DetailLine("Safety checks", it.joinToString("\n") { c -> "✓ $c" }) }
                b.error?.let { DetailLine("What went wrong", it) }
                Spacer(Modifier.height(8.dp))
                Text("Build log", style = MaterialTheme.typography.labelMedium, color = Ui.Text2)
                Spacer(Modifier.height(6.dp))
                Box(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(14.dp))
                        .background(Ui.Soft)
                        .horizontalScroll(rememberScrollState())
                        .padding(12.dp),
                ) {
                    Text(log.lines().takeLast(120).joinToString("\n").ifBlank { "Loading…" }, style = Mono, softWrap = false)
                }
            }
        }
    }
}

@Composable
private fun DetailLine(label: String, value: String) {
    Column(Modifier.padding(bottom = 14.dp)) {
        Text(label, style = MaterialTheme.typography.labelMedium, color = Ui.Text2)
        Spacer(Modifier.height(2.dp))
        Text(value, style = MaterialTheme.typography.bodySmall, color = Ui.Text)
    }
}
