// GENESIS PROTECTED FILE — server-controlled entry point.
// Generated code must provide `@Composable fun GenesisApp()` in package com.genesis.app.
package com.genesis.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.genesis.app.ui.theme.GenesisTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            GenesisTheme {
                GenesisApp()
            }
        }
    }
}
