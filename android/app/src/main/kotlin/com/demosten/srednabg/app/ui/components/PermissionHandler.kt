// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.components

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat

data class PermissionState(
    val fineLocationGranted: Boolean = false,
    val backgroundLocationGranted: Boolean = false,
    val notificationGranted: Boolean = false,
) {
    val locationReady: Boolean get() = fineLocationGranted
}

@Composable
fun rememberPermissionHandler(): PermissionState {
    val context = LocalContext.current
    var state by remember { mutableStateOf(PermissionState()) }

    fun checkPermissions() {
        state = PermissionState(
            fineLocationGranted = ContextCompat.checkSelfPermission(
                context, Manifest.permission.ACCESS_FINE_LOCATION,
            ) == PackageManager.PERMISSION_GRANTED,
            backgroundLocationGranted = ContextCompat.checkSelfPermission(
                context, Manifest.permission.ACCESS_BACKGROUND_LOCATION,
            ) == PackageManager.PERMISSION_GRANTED,
            notificationGranted = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                ContextCompat.checkSelfPermission(
                    context, Manifest.permission.POST_NOTIFICATIONS,
                ) == PackageManager.PERMISSION_GRANTED
            } else {
                true
            },
        )
    }

    val backgroundLocationLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { checkPermissions() }

    val notificationLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) {
        checkPermissions()
        if (state.fineLocationGranted && !state.backgroundLocationGranted) {
            backgroundLocationLauncher.launch(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
        }
    }

    val locationLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) {
        checkPermissions()
        if (state.fineLocationGranted) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && !state.notificationGranted) {
                notificationLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            } else if (!state.backgroundLocationGranted) {
                backgroundLocationLauncher.launch(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
            }
        }
    }

    LaunchedEffect(Unit) {
        checkPermissions()
        if (!state.fineLocationGranted) {
            locationLauncher.launch(
                arrayOf(
                    Manifest.permission.ACCESS_FINE_LOCATION,
                    Manifest.permission.ACCESS_COARSE_LOCATION,
                ),
            )
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && !state.notificationGranted) {
            notificationLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        } else if (!state.backgroundLocationGranted) {
            backgroundLocationLauncher.launch(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
        }
    }

    return state
}
