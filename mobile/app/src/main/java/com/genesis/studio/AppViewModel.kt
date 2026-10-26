package com.genesis.studio

import android.app.Application
import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.genesis.studio.data.ApiException
import com.genesis.studio.data.Build
import com.genesis.studio.data.GenesisApi
import com.genesis.studio.data.Health
import com.genesis.studio.data.Installer
import kotlinx.coroutines.launch
import java.io.File

sealed interface DownloadState {
    data object Idle : DownloadState
    data class Downloading(val progress: Float) : DownloadState
    data class Ready(val file: File) : DownloadState
    data class Failed(val message: String) : DownloadState
}

class AppViewModel(app: Application) : AndroidViewModel(app) {
    private val prefs = app.getSharedPreferences("genesis", Context.MODE_PRIVATE)

    var api by mutableStateOf(loadApi())
        private set
    var health by mutableStateOf<Health?>(null)
        private set
    var builds by mutableStateOf<List<Build>>(emptyList())
        private set
    var buildsLoading by mutableStateOf(false)
        private set
    var buildsError by mutableStateOf<String?>(null)
        private set
    var connecting by mutableStateOf(false)
        private set
    var connectError by mutableStateOf<String?>(null)
    var creating by mutableStateOf(false)
        private set
    var createError by mutableStateOf<String?>(null)
    var notice by mutableStateOf<String?>(null)

    /** Server + code from a genesis://pair link, shown pre-filled on the connect screen. */
    var pendingPairing by mutableStateOf<Pair<String, String>?>(null)

    val downloads = mutableStateMapOf<String, DownloadState>()

    val savedServer: String get() = prefs.getString("server", "") ?: ""

    init {
        if (api != null) refresh()
    }

    private fun loadApi(): GenesisApi? {
        val server = prefs.getString("server", null) ?: return null
        val code = prefs.getString("code", null) ?: return null
        return GenesisApi(server, code)
    }

    fun connect(serverInput: String, codeInput: String) {
        val server = GenesisApi.normalizeServer(serverInput)
        val code = GenesisApi.formatCode(codeInput)
        if (server == null) {
            connectError = "Enter the address shown on your computer, like 192.168.1.20:8765"
            return
        }
        if (code.length < 14) {
            connectError = "Enter the 16-character code shown on your computer"
            return
        }
        connecting = true
        connectError = null
        viewModelScope.launch {
            val candidate = GenesisApi(server, code)
            try {
                health = candidate.health()
                prefs.edit().putString("server", server).putString("code", code).apply()
                api = candidate
                pendingPairing = null
                refresh()
            } catch (e: ApiException) {
                connectError = e.message
            } finally {
                connecting = false
            }
        }
    }

    fun disconnect() {
        prefs.edit().remove("code").apply()
        api = null
        health = null
        builds = emptyList()
        downloads.clear()
    }

    fun refresh() {
        val current = api ?: return
        buildsLoading = true
        viewModelScope.launch {
            try {
                builds = current.builds()
                buildsError = null
                if (health == null) health = runCatching { current.health() }.getOrNull()
            } catch (e: ApiException) {
                buildsError = e.message
                if (e.status == 401) disconnect().also { connectError = "Please connect again — the code on your computer changed." }
            } finally {
                buildsLoading = false
            }
        }
    }

    fun refreshHealth() {
        val current = api ?: return
        viewModelScope.launch { health = runCatching { current.health() }.getOrNull() }
    }

    fun create(prompt: String, appName: String?, onCreated: (String) -> Unit) {
        val current = api ?: return
        creating = true
        createError = null
        viewModelScope.launch {
            try {
                val build = current.create(prompt.trim(), appName?.trim()?.takeIf { it.isNotEmpty() })
                builds = listOf(build) + builds.filterNot { it.id == build.id }
                onCreated(build.id)
            } catch (e: ApiException) {
                createError = e.message
            } finally {
                creating = false
            }
        }
    }

    suspend fun fetchBuild(id: String): Build? {
        val current = api ?: return null
        val b = current.build(id)
        builds = builds.map { if (it.id == id) b else it }.let { list -> if (list.any { it.id == id }) list else listOf(b) + list }
        return b
    }

    suspend fun fetchLog(id: String): String = api?.log(id) ?: ""

    private fun apkFile(build: Build): File? {
        val name = build.apk?.filename?.filter { it.isLetterOrDigit() || it == '-' || it == '.' } ?: return null
        return File(Installer.apkDir(getApplication()), name)
    }

    /** Download (once) then open the system installer. */
    fun install(build: Build, context: Context) = withApk(build) { file ->
        if (!Installer.canInstall(context)) {
            notice = "Turn on “Allow from this source”, then come back and tap Install again."
            Installer.openInstallPermissionSettings(context)
        } else {
            Installer.install(context, file)
        }
    }

    fun share(build: Build, context: Context) = withApk(build) { file ->
        Installer.share(context, file, build.displayName)
    }

    private fun withApk(build: Build, then: (File) -> Unit) {
        val current = api ?: return
        val file = apkFile(build) ?: return
        if (file.isFile && file.length() == build.apk?.size) {
            downloads[build.id] = DownloadState.Ready(file)
            then(file)
            return
        }
        if (downloads[build.id] is DownloadState.Downloading) return
        downloads[build.id] = DownloadState.Downloading(0f)
        viewModelScope.launch {
            try {
                current.downloadApk(build.id, file) { p -> downloads[build.id] = DownloadState.Downloading(p) }
                downloads[build.id] = DownloadState.Ready(file)
                then(file)
            } catch (e: ApiException) {
                downloads[build.id] = DownloadState.Failed(e.message ?: "Download failed")
            }
        }
    }
}
