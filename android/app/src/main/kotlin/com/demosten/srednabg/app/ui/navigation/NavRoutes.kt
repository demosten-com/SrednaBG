// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Map
import androidx.compose.material.icons.filled.Settings
import androidx.compose.ui.graphics.vector.ImageVector
import com.demosten.srednabg.R

sealed class NavRoute(
    val route: String,
    val titleResId: Int,
    val icon: ImageVector,
) {
    data object Home : NavRoute("home", R.string.nav_home, Icons.Default.Home)
    data object Map : NavRoute("map", R.string.nav_map, Icons.Default.Map)
    data object Settings : NavRoute("settings", R.string.nav_settings, Icons.Default.Settings)
    data object History : NavRoute("history", R.string.nav_history, Icons.Default.History)

    companion object {
        // TODO: Re-add History when TripHistoryScreen is implemented
        val all = listOf(Home, Map, Settings)
    }
}
