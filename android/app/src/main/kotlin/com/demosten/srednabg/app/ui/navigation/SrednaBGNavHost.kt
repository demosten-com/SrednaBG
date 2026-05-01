// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.navigation

import androidx.compose.animation.EnterTransition
import androidx.compose.animation.ExitTransition
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import com.demosten.srednabg.app.ui.screens.HomeScreen
import com.demosten.srednabg.app.ui.screens.SettingsScreen
import com.demosten.srednabg.app.ui.screens.ZoneMapScreen

@Composable
fun SrednaBGNavHost(navController: NavHostController, modifier: Modifier = Modifier) {
    NavHost(
        navController = navController,
        startDestination = NavRoute.Home.route,
        modifier = modifier,
        enterTransition = { EnterTransition.None },
        exitTransition = { ExitTransition.None },
        popEnterTransition = { EnterTransition.None },
        popExitTransition = { ExitTransition.None },
    ) {
        composable(NavRoute.Home.route) { HomeScreen() }
        composable(NavRoute.Map.route) { ZoneMapScreen() }
        composable(NavRoute.Settings.route) { SettingsScreen() }
        // TODO: Re-add when TripHistoryScreen is implemented
        // composable(NavRoute.History.route) { TripHistoryScreen() }
    }
}
