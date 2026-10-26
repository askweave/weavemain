package com.genesis.studio

import android.content.Intent
import android.graphics.Color as AndroidColor
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import com.genesis.studio.data.GenesisApi
import com.genesis.studio.ui.screens.BuildScreen
import com.genesis.studio.ui.screens.ConnectScreen
import com.genesis.studio.ui.screens.HomeScreen
import com.genesis.studio.ui.screens.SettingsScreen
import com.genesis.studio.ui.theme.GenesisTheme

class MainActivity : ComponentActivity() {
    private val vm: AppViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.light(AndroidColor.TRANSPARENT, AndroidColor.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.light(AndroidColor.TRANSPARENT, AndroidColor.TRANSPARENT),
        )
        handlePairing(intent)
        setContent { GenesisTheme { GenesisRoot(vm) } }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handlePairing(intent)
    }

    /** genesis://pair?u=...&c=... from the computer's QR code: pre-fill and connect. */
    private fun handlePairing(intent: Intent?) {
        val link = intent?.dataString ?: return
        val pairing = GenesisApi.parsePairingLink(link) ?: return
        if (vm.api != null) vm.disconnect()
        vm.pendingPairing = pairing
    }
}

/** "home", "settings" or "app:<id>". */
@Composable
fun GenesisRoot(vm: AppViewModel) {
    if (vm.api == null) {
        ConnectScreen(vm)
        return
    }
    var screen by rememberSaveable { mutableStateOf("home") }
    val goHome = { screen = "home"; vm.notice = null; vm.refresh() }

    AnimatedContent(
        targetState = screen,
        transitionSpec = {
            if (targetState != "home") {
                (slideInHorizontally(tween(300)) { it / 4 } + fadeIn(tween(300))) togetherWith fadeOut(tween(180))
            } else {
                fadeIn(tween(240)) togetherWith (slideOutHorizontally(tween(260)) { it / 4 } + fadeOut(tween(180)))
            }
        },
        label = "root",
    ) { s ->
        when {
            s == "settings" -> SettingsScreen(vm, onBack = goHome)
            s.startsWith("app:") -> BuildScreen(vm, s.removePrefix("app:"), onBack = goHome, onOpenBuild = { screen = "app:$it" })
            else -> HomeScreen(vm, onOpenBuild = { screen = "app:$it" }, onOpenSettings = { screen = "settings" })
        }
    }
}
