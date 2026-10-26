// Template sample (also the design-kit smoke test). Replaced by generated code for every Genesis build.
package com.genesis.app

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.Checkbox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import com.genesis.app.ui.kit.BarChart
import com.genesis.app.ui.kit.BottomTabs
import com.genesis.app.ui.kit.GenesisFab
import com.genesis.app.ui.kit.GenesisScreen
import com.genesis.app.ui.kit.HeroCard
import com.genesis.app.ui.kit.ItemCard
import com.genesis.app.ui.kit.ProgressRing
import com.genesis.app.ui.kit.SectionHeader
import com.genesis.app.ui.kit.StatRow
import com.genesis.app.ui.kit.StatTile
import com.genesis.app.ui.kit.SurfaceCard
import com.genesis.app.ui.kit.accentFor

private data class Habit(val name: String, val streak: Int)

@Composable
fun GenesisApp() {
    var tab by rememberSaveable { mutableIntStateOf(0) }
    val habits = remember { listOf(Habit("Morning run", 12), Habit("Read 20 pages", 5), Habit("Drink water", 21), Habit("Meditate", 3)) }
    val done = remember { mutableStateListOf(true, false, true, false) }
    val doneCount = done.count { it }

    GenesisScreen(
        title = "Today",
        subtitle = "Keep the streak alive",
        floatingAction = { GenesisFab(Icons.Filled.Add, onClick = {}, label = "New habit") },
        bottomBar = {
            BottomTabs(
                tabs = listOf("Today" to Icons.Filled.Home, "Stats" to Icons.Filled.DateRange, "Settings" to Icons.Filled.Settings),
                selected = tab,
                onSelect = { tab = it },
            )
        },
    ) {
        item {
            HeroCard(
                title = "Daily progress",
                value = "$doneCount of ${habits.size}",
                caption = "habits completed today",
                icon = Icons.Filled.CheckCircle,
                progress = doneCount / habits.size.toFloat(),
            )
        }
        item {
            StatRow {
                StatTile("Best streak", "21 days", Modifier.weight(1f), icon = Icons.Filled.Star, accent = accentFor(4))
                StatTile("This week", "86%", Modifier.weight(1f), icon = Icons.Filled.DateRange, accent = accentFor(1))
            }
        }
        item { SectionHeader("Habits", action = "See all", onAction = {}) }
        itemsIndexed(habits) { i, habit ->
            ItemCard(
                title = habit.name,
                subtitle = "${habit.streak}-day streak",
                badgeText = habit.name.take(1),
                accent = accentFor(i),
                onClick = { done[i] = !done[i] },
                trailing = { Checkbox(checked = done[i], onCheckedChange = { done[i] = it }) },
            )
        }
        item { SectionHeader("Last 7 days") }
        item {
            SurfaceCard {
                BarChart(
                    values = listOf(3f, 4f, 2f, 4f, 3f, 1f, doneCount.toFloat()),
                    labels = listOf("M", "T", "W", "T", "F", "S", "S"),
                )
            }
        }
        item {
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                ProgressRing(progress = 0.86f, label = "86%", caption = "weekly goal")
            }
        }
    }
}
