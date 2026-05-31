// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app (aosp flavor)

package com.demosten.srednabg.app.service

import android.content.Context
import android.location.LocationManager
import android.util.Log

private const val TAG = LOC_SRC_TAG

/**
 * aosp-flavor location-source factory. Always returns [SystemLocationSource]
 * (platform [LocationManager]) — this variant has no dependency on Google Play
 * Services, so there is no FusedLocationProvider to choose. Shipped to F-Droid
 * and GitHub Releases.
 */
fun createLocationSource(
    context: Context,
    listener: LocationUpdateListener,
): LocationSource {
    Log.d(TAG, "Selecting SystemLocationSource (aosp flavor)")
    val lm = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
    return SystemLocationSource(lm, listener)
}
