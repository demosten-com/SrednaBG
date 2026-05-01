// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.service

import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Build
import android.os.Bundle
import android.os.Looper
import android.util.Log
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.Priority

private const val TAG = "SrednaBG.LocSrc"

fun interface LocationUpdateListener {
    fun onLocation(location: Location)
}

/**
 * Provider-agnostic GPS source. Implementations wrap either Google Play's
 * FusedLocationProviderClient (phones) or the system LocationManager (AAOS,
 * where FLP often registers successfully but never delivers fixes).
 */
interface LocationSource {
    /** Start or update the desired delivery interval. Idempotent. */
    fun requestUpdates(intervalMs: Long)
    fun stop()
}

fun createLocationSource(
    context: Context,
    fusedClient: FusedLocationProviderClient,
    listener: LocationUpdateListener,
): LocationSource {
    val pm = context.packageManager
    val isAutomotive = pm.hasSystemFeature(PackageManager.FEATURE_AUTOMOTIVE)
    return if (isAutomotive) {
        Log.d(TAG, "Selecting SystemLocationSource (FEATURE_AUTOMOTIVE)")
        val lm = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        SystemLocationSource(lm, listener)
    } else {
        Log.d(TAG, "Selecting FusedLocationSource")
        FusedLocationSource(fusedClient, listener)
    }
}

class FusedLocationSource(
    private val client: FusedLocationProviderClient,
    private val listener: LocationUpdateListener,
) : LocationSource {

    private val callback = object : LocationCallback() {
        override fun onLocationResult(result: LocationResult) {
            result.lastLocation?.let(listener::onLocation)
        }
    }

    @Suppress("MissingPermission")
    override fun requestUpdates(intervalMs: Long) {
        client.removeLocationUpdates(callback)
        val request = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, intervalMs)
            .setMinUpdateIntervalMillis(intervalMs / 2)
            .build()
        client.requestLocationUpdates(request, callback, Looper.getMainLooper())
            .addOnSuccessListener { Log.d(TAG, "FLP requestLocationUpdates: success (intervalMs=$intervalMs)") }
            .addOnFailureListener { e -> Log.e(TAG, "FLP requestLocationUpdates FAILED", e) }
    }

    override fun stop() {
        client.removeLocationUpdates(callback)
    }
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
