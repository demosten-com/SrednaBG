// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.components

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import com.demosten.srednabg.app.permissions.PermissionRepository

/**
 * First-launch permission prompt sequence. Auto-chains the location pair
 * (fine → background) because they're conceptually one permission split by
 * Android into two prompts; firing them back-to-back keeps the user in
 * "answer the location questions" mode.
 *
 * Notifications are intentionally NOT auto-chained from here. Surfacing the
 * `POST_NOTIFICATIONS` system dialog with no in-app context confused users —
 * they'd assume it was unrelated to tracking, decline, and end up stranded.
 * The Home screen now drives notification grant via a dedicated card whose
 * body explains why it matters; the user taps Allow there to fire the system
 * dialog with full context.
 */
@Composable
fun rememberPermissionHandler(repository: PermissionRepository) {
    fun refresh() = repository.refresh()

    val backgroundLocationLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { refresh() }

    val locationLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) {
        refresh()
        val state = repository.state.value
        if (state.fineLocationGranted && !state.backgroundLocationGranted) {
            backgroundLocationLauncher.launch(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
        }
    }

    LaunchedEffect(Unit) {
        refresh()
        val state = repository.state.value
        if (!state.fineLocationGranted) {
            locationLauncher.launch(
                arrayOf(
                    Manifest.permission.ACCESS_FINE_LOCATION,
                    Manifest.permission.ACCESS_COARSE_LOCATION,
                ),
            )
        } else if (!state.backgroundLocationGranted) {
            backgroundLocationLauncher.launch(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
        }
    }
}
