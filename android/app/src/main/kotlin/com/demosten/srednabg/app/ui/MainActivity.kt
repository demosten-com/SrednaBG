// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui

import android.content.pm.ActivityInfo
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.core.view.WindowCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.demosten.srednabg.app.permissions.PermissionRepository
import com.demosten.srednabg.app.service.LocationTrackingService
import com.demosten.srednabg.app.ui.components.PermissionHandler
import com.demosten.srednabg.app.ui.navigation.NavRoute
import com.demosten.srednabg.app.ui.navigation.SrednaBGNavHost
import com.demosten.srednabg.app.ui.theme.SrednaBGTheme
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : AppCompatActivity() {

    @Inject lateinit var permissionRepository: PermissionRepository

    @OptIn(ExperimentalComposeUiApi::class)
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Edge-to-edge globally with permanently transparent system bars.
        // The status bar shows through to whatever is at the top of the
        // current screen — map tiles on Map, the screen background on
        // Home/Settings — without resizing the layout when tabs change.
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.auto(
                android.graphics.Color.TRANSPARENT,
                android.graphics.Color.TRANSPARENT,
            ),
            navigationBarStyle = SystemBarStyle.auto(
                android.graphics.Color.TRANSPARENT,
                android.graphics.Color.TRANSPARENT,
            ),
        )
        setContent {
            SrednaBGTheme {
                val navController = rememberNavController()
                val navBackStackEntry by navController.currentBackStackEntryAsState()
                val currentDestination = navBackStackEntry?.destination
                val isMapRoute = currentDestination?.hierarchy?.any {
                    it.route == NavRoute.Map.route
                } == true

                PermissionHandler(permissionRepository)

                // Drive status-bar icon contrast from the device theme on
                // Home/Settings. Map overrides this from its resolved MapTheme
                // (see ZoneMapScreen) and restores the captured value on exit.
                val darkTheme = isSystemInDarkTheme()
                val view = LocalView.current
                if (!view.isInEditMode && !isMapRoute) {
                    SideEffect {
                        val window = (view.context as android.app.Activity).window
                        WindowCompat.getInsetsController(window, view)
                            .isAppearanceLightStatusBars = !darkTheme
                    }
                }

                // Lock every non-Map screen (Home, History + its detail,
                // Settings) to portrait — none was designed for landscape —
                // while letting the Map tab free-rotate. Driven from the route
                // here (a single source of truth) rather than per-screen, so
                // swapping between portrait screens can't race a
                // restore-on-dispose back to free-rotate.
                // userPortrait: honors the system auto-rotate lock.
                DisposableEffect(isMapRoute, view) {
                    val activity = view.context as? android.app.Activity
                    if (activity != null && !view.isInEditMode) {
                        activity.requestedOrientation = if (isMapRoute) {
                            ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
                        } else {
                            ActivityInfo.SCREEN_ORIENTATION_USER_PORTRAIT
                        }
                    }
                    onDispose {
                        if (activity != null && !view.isInEditMode) {
                            activity.requestedOrientation =
                                ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
                        }
                    }
                }

                // Keep the screen awake while tracking is active, on any tab.
                // Tied to the activity window so tab switches don't introduce a
                // brief sleep window. Cleared on dispose so the flag never
                // outlives the activity if tracking is still on at teardown.
                val isTracking by LocationTrackingService.isTracking.collectAsStateWithLifecycle()
                DisposableEffect(isTracking, view) {
                    val activity = view.context as? android.app.Activity
                    if (activity != null && !view.isInEditMode) {
                        if (isTracking) {
                            activity.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                        } else {
                            activity.window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                        }
                    }
                    onDispose {
                        if (activity != null && !view.isInEditMode) {
                            activity.window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                        }
                    }
                }

                Scaffold(
                    // Constant inset configuration on every tab so switching
                    // routes never reflows the layout. Home/Settings nest their
                    // own Scaffold which adds the status-bar inset; ZoneMapScreen
                    // fills the area and lets the map paint behind the
                    // transparent status bar.
                    contentWindowInsets = WindowInsets(0),
                    bottomBar = {
                        NavigationBar(
                            modifier = Modifier.semantics { testTagsAsResourceId = true },
                        ) {
                            NavRoute.all.forEach { route ->
                                NavigationBarItem(
                                    modifier = Modifier.testTag("tab-${route.route}"),
                                    icon = { route.TabIcon(contentDescription = stringResource(route.titleResId)) },
                                    label = { Text(stringResource(route.titleResId)) },
                                    selected = currentDestination?.hierarchy?.any {
                                        it.route == route.route
                                    } == true,
                                    onClick = {
                                        navController.navigate(route.route) {
                                            popUpTo(navController.graph.startDestinationId) {
                                                saveState = true
                                            }
                                            launchSingleTop = true
                                            restoreState = true
                                        }
                                    },
                                )
                            }
                        }
                    },
                ) { innerPadding ->
                    SrednaBGNavHost(
                        navController = navController,
                        modifier = Modifier.padding(innerPadding),
                    )
                }
            }
        }
    }
}
