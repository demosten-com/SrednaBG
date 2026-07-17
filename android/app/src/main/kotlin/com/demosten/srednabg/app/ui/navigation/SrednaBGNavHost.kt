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
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.demosten.srednabg.app.ui.screens.HistoryDetailScreen
import com.demosten.srednabg.app.ui.screens.HomeScreen
import com.demosten.srednabg.app.ui.screens.SettingsScreen
import com.demosten.srednabg.app.ui.screens.TripHistoryScreen
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
        composable(NavRoute.History.route) {
            TripHistoryScreen(
                onItemClick = { id -> navController.navigate("history/$id") },
            )
        }
        composable(
            route = "history/{id}",
            arguments = listOf(navArgument("id") { type = NavType.StringType }),
        ) { backStackEntry ->
            HistoryDetailScreen(
                id = backStackEntry.arguments?.getString("id").orEmpty(),
                onBack = { navController.popBackStack() },
                onShowOnMap = {
                    // Same options as MainActivity's tab clicks so the bottom
                    // bar selection and saved tab states stay consistent.
                    navController.navigate(NavRoute.Map.route) {
                        popUpTo(navController.graph.startDestinationId) { saveState = true }
                        launchSingleTop = true
                        restoreState = true
                    }
                },
            )
        }
    }
}
