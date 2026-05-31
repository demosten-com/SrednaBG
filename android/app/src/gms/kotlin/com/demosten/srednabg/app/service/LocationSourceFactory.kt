// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app (gms flavor)

package com.demosten.srednabg.app.service

import android.content.Context
import android.content.pm.PackageManager
import android.location.LocationManager
import android.os.Looper
import android.util.Log
import com.google.android.gms.common.ConnectionResult
import com.google.android.gms.common.GoogleApiAvailability
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority

private const val TAG = LOC_SRC_TAG

/** Which concrete [LocationSource] the gms flavor should use. */
internal enum class LocationSourceKind { FUSED, SYSTEM }

/**
 * Pure selection policy for the gms flavor, extracted from Android framework
 * calls so it can be unit-tested without a device.
 *
 * FusedLocationProvider needs working Google Play Services. We fall back to the
 * platform [LocationManager] when either:
 *   - the device is Android Automotive (FLP frequently registers but never
 *     delivers fixes there), or
 *   - Play Services is missing / disabled / too old (e.g. someone sideloads the
 *     gms APK onto a de-Googled phone). Without this, FLP would silently never
 *     deliver a fix and the app would look broken.
 */
internal fun chooseLocationSourceKind(
    isAutomotive: Boolean,
    isGmsAvailable: Boolean,
): LocationSourceKind =
    if (isAutomotive || !isGmsAvailable) LocationSourceKind.SYSTEM else LocationSourceKind.FUSED

/**
 * gms-flavor location-source factory. Uses [FusedLocationSource] where Play
 * Services is usable, otherwise falls back to [SystemLocationSource]. Shipped
 * to the Play Store.
 */
fun createLocationSource(
    context: Context,
    listener: LocationUpdateListener,
): LocationSource {
    val isAutomotive =
        context.packageManager.hasSystemFeature(PackageManager.FEATURE_AUTOMOTIVE)
    val isGmsAvailable = GoogleApiAvailability.getInstance()
        .isGooglePlayServicesAvailable(context) == ConnectionResult.SUCCESS

    return when (chooseLocationSourceKind(isAutomotive, isGmsAvailable)) {
        LocationSourceKind.FUSED -> {
            Log.d(TAG, "Selecting FusedLocationSource (gms flavor)")
            FusedLocationSource(
                LocationServices.getFusedLocationProviderClient(context),
                listener,
            )
        }
        LocationSourceKind.SYSTEM -> {
            Log.d(
                TAG,
                "Selecting SystemLocationSource (gms flavor fallback; " +
                    "automotive=$isAutomotive gmsAvailable=$isGmsAvailable)",
            )
            val lm = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
            SystemLocationSource(lm, listener)
        }
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
