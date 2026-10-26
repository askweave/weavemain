package com.genesis.studio.ui.screens

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
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
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.genesis.studio.AppViewModel
import com.genesis.studio.ui.components.AppMark
import com.genesis.studio.ui.components.CircleIconButton
import com.genesis.studio.ui.components.QuietButton
import com.genesis.studio.ui.components.SoftCard
import com.genesis.studio.ui.theme.Ui
import androidx.compose.foundation.layout.Box

@Composable
fun SettingsScreen(vm: AppViewModel, onBack: () -> Unit) {
    BackHandler(onBack = onBack)
    LaunchedEffect(Unit) { vm.refreshHealth() }
    val health = vm.health
    val online = health?.ready == true

    Column(
        Modifier
            .fillMaxSize()
            .background(Ui.Bg)
            .statusBarsPadding()
            .navigationBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 22.dp),
    ) {
        Spacer(Modifier.height(8.dp))
        CircleIconButton(Icons.AutoMirrored.Filled.ArrowBack, "Back", onBack)
        Spacer(Modifier.height(24.dp))
        Text("Settings", style = MaterialTheme.typography.displaySmall, color = Ui.Text)
        Spacer(Modifier.height(24.dp))

        SoftCard {
            Text("Connected computer", style = MaterialTheme.typography.labelMedium, color = Ui.Text2)
            Spacer(Modifier.height(6.dp))
            Text(vm.api?.baseUrl?.removePrefix("http://") ?: "—", style = MaterialTheme.typography.titleMedium, color = Ui.Text)
            Spacer(Modifier.height(14.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(10.dp).clip(CircleShape).background(if (online) Ui.Green else if (health == null) Ui.Text3 else Ui.Amber))
                Spacer(Modifier.width(10.dp))
                Text(
                    when {
                        health == null -> "Checking…"
                        online -> "Connected and ready"
                        else -> "Connected, but your computer needs setup"
                    },
                    style = MaterialTheme.typography.bodyMedium,
                    color = Ui.Text2,
                )
            }
            val firstProblem = health?.checks?.firstOrNull { !it.ok }
            if (firstProblem != null) {
                Spacer(Modifier.height(10.dp))
                Text("${firstProblem.name}: ${firstProblem.fix.ifBlank { firstProblem.detail }}", style = MaterialTheme.typography.bodySmall, color = Ui.Amber)
            }
        }
        Spacer(Modifier.height(16.dp))
        QuietButton("Check connection", onClick = { vm.refreshHealth(); vm.refresh() }, icon = Icons.Filled.Refresh)
        Spacer(Modifier.height(10.dp))
        QuietButton("Disconnect this phone", onClick = vm::disconnect, icon = Icons.Filled.Close, textColor = Ui.Red)

        Spacer(Modifier.height(48.dp))
        Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
            AppMark(22.dp)
            Spacer(Modifier.height(10.dp))
            Text("Genesis 1.1", style = MaterialTheme.typography.labelMedium, color = Ui.Text2)
            Spacer(Modifier.height(4.dp))
            Text(
                "Apps are designed by AI and built on your computer. Your phone only stores the address and code.",
                style = MaterialTheme.typography.bodySmall,
                color = Ui.Text3,
                textAlign = TextAlign.Center,
            )
        }
        Spacer(Modifier.height(32.dp))
    }
}
