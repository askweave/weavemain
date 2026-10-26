package com.genesis.studio.ui.screens

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.speech.RecognizerIntent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.genesis.studio.AppViewModel
import com.genesis.studio.data.Build
import com.genesis.studio.ui.components.AppIcon
import com.genesis.studio.ui.components.AppMark
import com.genesis.studio.ui.components.BigButton
import com.genesis.studio.ui.components.CircleIconButton
import com.genesis.studio.ui.components.InputBox
import com.genesis.studio.ui.components.SectionTitle
import com.genesis.studio.ui.components.SoftCard
import com.genesis.studio.ui.components.SpeakButton
import com.genesis.studio.ui.components.StatusPill
import com.genesis.studio.ui.components.Suggestion
import com.genesis.studio.ui.theme.Ui
import java.time.Duration
import java.time.OffsetDateTime

private data class Idea(val emoji: String, val label: String, val prompt: String)

private val IDEAS = listOf(
    Idea("💧", "Water tracker", "A simple app to track how many glasses of water I drink each day, with a daily goal."),
    Idea("✅", "Habits", "A habit tracker with daily check-ins, streaks and a 7-day view. Let me add, rename and delete habits."),
    Idea("💪", "Workouts", "A gym log to record my exercises, sets and weights, with a history and progress chart."),
    Idea("📝", "To-do list", "A to-do list with due dates and priorities, and filters for today, upcoming and done."),
    Idea("🃏", "Flashcards", "A flashcards app: make decks, add cards, and study with a flip animation."),
    Idea("🧮", "Calculator", "A clean calculator with big buttons, percentages and a history of past calculations."),
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(vm: AppViewModel, onOpenBuild: (String) -> Unit, onOpenSettings: () -> Unit) {
    var prompt by rememberSaveable { mutableStateOf("") }
    var name by rememberSaveable { mutableStateOf("") }
    var showName by rememberSaveable { mutableStateOf(false) }
    val tooShort = prompt.isNotBlank() && prompt.trim().length < 10
    var voiceError by remember { mutableStateOf<String?>(null) }
    // Uses the phone's own voice typing screen, so Genesis needs no microphone permission.
    val speech = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val heard = result.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()?.trim()
        if (result.resultCode == Activity.RESULT_OK && !heard.isNullOrEmpty()) {
            val spoken = heard.replaceFirstChar { it.uppercase() }
            prompt = (if (prompt.isBlank()) spoken else prompt.trimEnd() + " " + spoken).take(4000)
        }
    }

    PullToRefreshBox(
        isRefreshing = vm.buildsLoading,
        onRefresh = vm::refresh,
        modifier = Modifier.fillMaxSize().background(Ui.Bg),
    ) {
        LazyColumn(
            Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().imePadding(),
            contentPadding = PaddingValues(start = 22.dp, end = 22.dp, top = 8.dp, bottom = 40.dp),
        ) {
            item {
                Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                    AppMark(22.dp)
                    Spacer(Modifier.width(10.dp))
                    Text("Genesis", style = MaterialTheme.typography.titleMedium, color = Ui.Text, modifier = Modifier.weight(1f))
                    CircleIconButton(Icons.Filled.Settings, "Settings", onOpenSettings)
                }
            }
            item {
                Spacer(Modifier.height(28.dp))
                Text("What app do you want?", style = MaterialTheme.typography.displaySmall, color = Ui.Text)
                Spacer(Modifier.height(8.dp))
                Text("Describe it in your own words. We'll make it for you.", style = MaterialTheme.typography.bodyLarge, color = Ui.Text2)
                Spacer(Modifier.height(24.dp))
                Box {
                    InputBox(
                        value = prompt,
                        onValueChange = { if (it.length <= 4000) prompt = it },
                        placeholder = "e.g. An app to track how much water I drink each day",
                        singleLine = false,
                        minHeight = 150.dp,
                        keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
                        bottomSpace = 44.dp,
                    )
                    SpeakButton(
                        onClick = {
                            voiceError = null
                            val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                                .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                                .putExtra(RecognizerIntent.EXTRA_PROMPT, "Describe the app you want")
                            try {
                                speech.launch(intent)
                            } catch (e: ActivityNotFoundException) {
                                voiceError = "Voice typing isn't available on this phone. Try the mic on your keyboard instead."
                            }
                        },
                        modifier = Modifier.align(Alignment.BottomEnd).padding(12.dp),
                    )
                }
                voiceError?.let {
                    Text(it, style = MaterialTheme.typography.bodySmall, color = Ui.Text2, modifier = Modifier.padding(start = 6.dp, top = 8.dp))
                }
                if (tooShort) {
                    Text("Tell us a little more", style = MaterialTheme.typography.bodySmall, color = Ui.Text2, modifier = Modifier.padding(start = 6.dp, top = 8.dp))
                }
                Spacer(Modifier.height(14.dp))
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    IDEAS.forEach { idea -> Suggestion(idea.emoji, idea.label) { prompt = idea.prompt } }
                }
                Spacer(Modifier.height(14.dp))
                if (!showName) {
                    Text(
                        "+ Give it a name (optional)",
                        style = MaterialTheme.typography.labelMedium,
                        color = Ui.Accent,
                        modifier = Modifier.clip(RoundedCornerShape(12.dp)).clickable { showName = true }.padding(horizontal = 6.dp, vertical = 8.dp),
                    )
                }
                AnimatedVisibility(showName) {
                    InputBox(
                        value = name,
                        onValueChange = { if (it.length <= 30) name = it },
                        placeholder = "App name",
                        keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Words, imeAction = ImeAction.Done),
                    )
                }
                vm.createError?.let {
                    Spacer(Modifier.height(12.dp))
                    Text(it, style = MaterialTheme.typography.bodyMedium, color = Ui.Red)
                }
                Spacer(Modifier.height(18.dp))
                BigButton(
                    text = if (vm.creating) "Starting…" else "Make my app",
                    onClick = {
                        vm.create(prompt, name.takeIf { showName }) { id ->
                            prompt = ""; name = ""; showName = false
                            onOpenBuild(id)
                        }
                    },
                    enabled = prompt.trim().length >= 10,
                    loading = vm.creating,
                )
                Spacer(Modifier.height(40.dp))
                SectionTitle("Your apps")
                Spacer(Modifier.height(12.dp))
                vm.buildsError?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = Ui.Red, modifier = Modifier.padding(bottom = 12.dp)) }
            }
            if (vm.builds.isEmpty() && !vm.buildsLoading) {
                item {
                    SoftCard(background = Ui.Soft) {
                        Text("Apps you make will show up here.", style = MaterialTheme.typography.bodyMedium, color = Ui.Text2)
                    }
                }
            }
            items(vm.builds, key = { it.id }) { build ->
                AppRow(build) { onOpenBuild(build.id) }
                Spacer(Modifier.height(10.dp))
            }
        }
    }
}

@Composable
private fun AppRow(build: Build, onClick: () -> Unit) {
    SoftCard(onClick = onClick, padding = 14.dp) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            AppIcon(build.appName, build.primaryColor, 52.dp, busy = !build.isDone)
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    build.appName ?: "New app",
                    style = MaterialTheme.typography.titleMedium,
                    color = Ui.Text,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.height(4.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    StatusPill(build.status)
                    relativeTime(build.createdAt)?.let {
                        Spacer(Modifier.width(8.dp))
                        Text(it, style = MaterialTheme.typography.bodySmall, color = Ui.Text3)
                    }
                }
            }
            Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, null, tint = Ui.Text3)
        }
    }
}

fun relativeTime(iso: String): String? = try {
    val d = Duration.between(OffsetDateTime.parse(iso), OffsetDateTime.now())
    when {
        d.toMinutes() < 1 -> "just now"
        d.toMinutes() < 60 -> "${d.toMinutes()} min ago"
        d.toHours() < 24 -> "${d.toHours()} h ago"
        d.toDays() < 7 -> "${d.toDays()} d ago"
        else -> OffsetDateTime.parse(iso).toLocalDate().toString()
    }
} catch (e: Exception) {
    null
}
