// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Map
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Icon
import androidx.compose.runtime.Composable
import androidx.compose.ui.res.painterResource
import com.demosten.srednabg.R

sealed class NavRoute(
    val route: String,
    val titleResId: Int,
) {
    @Composable
    abstract fun TabIcon(contentDescription: String?)

    data object Home : NavRoute("home", R.string.nav_home) {
        @Composable
        override fun TabIcon(contentDescription: String?) {
            Icon(
                painter = painterResource(R.drawable.ic_home_tab),
                contentDescription = contentDescription,
            )
        }
    }

    data object Map : NavRoute("map", R.string.nav_map) {
        @Composable
        override fun TabIcon(contentDescription: String?) {
            Icon(
                imageVector = Icons.Default.Map,
                contentDescription = contentDescription,
            )
        }
    }

    data object Settings : NavRoute("settings", R.string.nav_settings) {
        @Composable
        override fun TabIcon(contentDescription: String?) {
            Icon(
                imageVector = Icons.Default.Settings,
                contentDescription = contentDescription,
            )
        }
    }

    data object History : NavRoute("history", R.string.nav_history) {
        @Composable
        override fun TabIcon(contentDescription: String?) {
            Icon(
                imageVector = Icons.Default.History,
                contentDescription = contentDescription,
            )
        }
    }

    companion object {
        // History sits between Map and Settings in the bottom bar.
        val all = listOf(Home, Map, History, Settings)
    }
}
