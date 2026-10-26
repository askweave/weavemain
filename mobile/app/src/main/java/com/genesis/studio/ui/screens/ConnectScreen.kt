package com.genesis.studio.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.genesis.studio.AppViewModel
import com.genesis.studio.data.GenesisApi
import com.genesis.studio.ui.components.AppMark
import com.genesis.studio.ui.components.BigButton
import com.genesis.studio.ui.components.InputBox
import com.genesis.studio.ui.components.SoftCard
import com.genesis.studio.ui.theme.Ui

@Composable
fun ConnectScreen(vm: AppViewModel) {
    var server by rememberSaveable { mutableStateOf(vm.savedServer.removePrefix("http://")) }
    var code by rememberSaveable { mutableStateOf("") }
    var showHelp by rememberSaveable { mutableStateOf(false) }

    LaunchedEffect(vm.pendingPairing) {
        vm.pendingPairing?.let { (s, c) ->
            server = s.removePrefix("http://")
            code = c
            vm.connect(s, c)
        }
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(Ui.Bg)
            .statusBarsPadding()
            .navigationBarsPadding()
            .imePadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(Modifier.height(72.dp))
        Box(
            Modifier.size(84.dp).clip(RoundedCornerShape(26.dp)).background(Ui.AccentSoft),
            contentAlignment = Alignment.Center,
        ) { AppMark(40.dp) }
        Spacer(Modifier.height(28.dp))
        Text("Welcome to Genesis", style = MaterialTheme.typography.displaySmall, color = Ui.Text, textAlign = TextAlign.Center)
        Spacer(Modifier.height(10.dp))
        Text(
            "Make your own apps just by describing them.",
            style = MaterialTheme.typography.bodyLarge,
            color = Ui.Text2,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(36.dp))

        SoftCard {
            InputBox(
                value = server,
                onValueChange = { server = it.trim() },
                placeholder = "192.168.1.20:8765",
                label = "Computer address",
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Next),
            )
            Spacer(Modifier.height(16.dp))
            InputBox(
                value = code,
                onValueChange = { code = GenesisApi.formatCode(it) },
                placeholder = "XXXX-XXXX-XXXX-XXXX",
                label = "Code",
                textStyle = MaterialTheme.typography.bodyLarge.copy(fontFamily = FontFamily.Monospace, letterSpacing = 1.sp),
                keyboardOptions = KeyboardOptions(
                    capitalization = KeyboardCapitalization.Characters,
                    keyboardType = KeyboardType.Ascii,
                    autoCorrectEnabled = false,
                    imeAction = ImeAction.Done,
                ),
            )
            vm.connectError?.let {
                Spacer(Modifier.height(14.dp))
                Text(it, style = MaterialTheme.typography.bodyMedium, color = Ui.Red)
            }
            Spacer(Modifier.height(20.dp))
            BigButton(
                text = if (vm.connecting) "Connecting" else "Connect",
                onClick = { vm.connect(server, code) },
                enabled = server.isNotBlank() && code.length >= 14,
                loading = vm.connecting,
            )
        }

        Spacer(Modifier.height(20.dp))
        Text(
            if (showHelp) "Hide help" else "Where do I find these?",
            style = MaterialTheme.typography.labelMedium,
            color = Ui.Accent,
            modifier = Modifier.clip(RoundedCornerShape(12.dp)).clickable { showHelp = !showHelp }.padding(12.dp),
        )
        AnimatedVisibility(showHelp) {
            SoftCard(background = Ui.Soft) {
                Text(
                    "Genesis makes apps on your computer, so your phone connects to it once.\n\n" +
                        "1.  On your computer, open Genesis and click “Connect phone”.\n" +
                        "2.  Type the address and code it shows, or just scan its QR code with your camera.\n" +
                        "3.  Keep your phone on the same Wi-Fi as your computer.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = Ui.Text2,
                )
            }
        }
        Spacer(Modifier.height(40.dp))
    }
}
