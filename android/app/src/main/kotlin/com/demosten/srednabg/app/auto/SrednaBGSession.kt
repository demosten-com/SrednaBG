// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.auto

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import androidx.car.app.Screen
import androidx.car.app.Session
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.demosten.srednabg.app.service.LocationTrackingService

class SrednaBGSession : Session() {

    companion object {
        @Volatile
        var isActive: Boolean = false
            private set
    }

    private var navigationScreen: NavigationScreen? = null

    override fun onCreateScreen(intent: Intent): Screen {
        val hasLocation = ContextCompat.checkSelfPermission(
            carContext, Manifest.permission.ACCESS_FINE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED
        if (hasLocation) {
            try {
                val serviceIntent = Intent(carContext, LocationTrackingService::class.java)
                ContextCompat.startForegroundService(carContext, serviceIntent)
            } catch (_: SecurityException) {}
        }

        val screen = NavigationScreen(carContext)
        navigationScreen = screen

        isActive = true
        lifecycle.addObserver(LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_DESTROY) {
                isActive = false
                navigationScreen?.cleanup()
                navigationScreen = null
            }
        })

        return screen
    }
}
