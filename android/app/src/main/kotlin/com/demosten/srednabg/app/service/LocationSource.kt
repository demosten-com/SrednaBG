// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.service

import android.content.Context
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Build
import android.os.Bundle
import android.os.Looper
import android.util.Log

/** Logcat tag for the location-source selection + system provider. The QA
 *  harness keys its flavor assertion off the "Selecting …LocationSource"
 *  lines emitted under this tag (see qa/parsers.py). */
const val LOC_SRC_TAG = "SrednaBG.LocSrc"

private const val TAG = LOC_SRC_TAG

fun interface LocationUpdateListener {
    fun onLocation(location: Location)
}

/**
 * Provider-agnostic GPS source. Implementations wrap either Google Play's
 * FusedLocationProviderClient (gms flavor) or the system LocationManager
 * (aosp flavor, and the gms flavor's fallback on AAOS / when Play Services
 * is unavailable).
 *
 * The factory that picks the implementation — `createLocationSource(context,
 * listener)` — is flavor-specific: see src/aosp/ and src/gms/. Keeping it out
 * of src/main/ is what lets the aosp variant compile without any GMS type.
 */
interface LocationSource {
    /** Start or update the desired delivery interval. Idempotent. */
    fun requestUpdates(intervalMs: Long)
    fun stop()
}

class SystemLocationSource(
    private val locationManager: LocationManager,
    private val listener: LocationUpdateListener,
) : LocationSource {

    private val androidListener = object : LocationListener {
        override fun onLocationChanged(location: Location) = listener.onLocation(location)
        override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) {}
        override fun onProviderEnabled(provider: String) {
            Log.d(TAG, "LocationManager provider enabled: $provider")
        }
        override fun onProviderDisabled(provider: String) {
            Log.d(TAG, "LocationManager provider disabled: $provider")
        }
    }

    @Suppress("MissingPermission")
    override fun requestUpdates(intervalMs: Long) {
        locationManager.removeUpdates(androidListener)

        val allProviders = runCatching { locationManager.allProviders }.getOrDefault(emptyList())
        val enabledProviders = runCatching { locationManager.getProviders(true) }.getOrDefault(emptyList())
        val isLocationEnabled = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            locationManager.isLocationEnabled.toString()
        } else {
            "n/a<P"
        }
        Log.d(TAG, "LocationManager providers: all=$allProviders enabled=$enabledProviders isLocationEnabled=$isLocationEnabled")

        val preferred = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
        val toUse = preferred.filter { it in enabledProviders }
            .ifEmpty { enabledProviders.filter { it != LocationManager.PASSIVE_PROVIDER } }

        if (toUse.isEmpty()) {
            Log.w(
                TAG,
                "LocationManager: no usable providers. Check (1) location permission for this app " +
                    "and (2) Settings → Location master toggle. allProviders=$allProviders",
            )
            return
        }
        try {
            toUse.forEach { provider ->
                locationManager.requestLocationUpdates(
                    provider,
                    intervalMs,
                    0f,
                    androidListener,
                    Looper.getMainLooper(),
                )
            }
            Log.d(TAG, "LocationManager requestLocationUpdates registered (providers=$toUse intervalMs=$intervalMs)")
        } catch (e: SecurityException) {
            Log.e(TAG, "LocationManager permission denied", e)
        }
    }

    override fun stop() {
        locationManager.removeUpdates(androidListener)
    }
}
