// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

import kotlin.math.PI
import kotlin.math.asin
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin

enum class MapThemeMode { AUTO, LIGHT, DARK }

enum class MapTheme { LIGHT, DARK }

/**
 * Picks the map theme to render given the user's preference, the user's
 * current GPS position (used as the observer location for sun-altitude in
 * AUTO mode), and the current UTC time.
 *
 * AUTO uses civil-twilight as the day/night gate (solar altitude > -6° →
 * LIGHT). This matches Google Maps / Waze / Apple Maps and avoids flipping
 * exactly at the visible horizon, which would feel premature when the sky
 * is still bright.
 *
 * If no GPS fix is available yet, AUTO falls back to Sofia's coordinates —
 * the app is Bulgaria-only, so the worst-case error in solar altitude
 * (Sofia → Vidin or Burgas) is well within the twilight margin.
 *
 * Hysteresis (e.g. 10-min debounce around the boundary) belongs in the
 * caller, not the resolver — the resolver stays pure so it can be unit-
 * tested with deterministic inputs.
 */
object MapThemeResolver {

    const val FALLBACK_LAT_SOFIA: Double = 42.7
    const val FALLBACK_LNG_SOFIA: Double = 23.3
    const val CIVIL_TWILIGHT_ALTITUDE_DEG: Double = -6.0

    fun resolve(mode: MapThemeMode, position: GpsPoint?, nowMillisUtc: Long): MapTheme {
        return when (mode) {
            MapThemeMode.LIGHT -> MapTheme.LIGHT
            MapThemeMode.DARK -> MapTheme.DARK
            MapThemeMode.AUTO -> {
                val lat = position?.lat ?: FALLBACK_LAT_SOFIA
                val lng = position?.lng ?: FALLBACK_LNG_SOFIA
                val altitudeDeg = solarAltitudeDegrees(lat, lng, nowMillisUtc)
                if (altitudeDeg > CIVIL_TWILIGHT_ALTITUDE_DEG) MapTheme.LIGHT else MapTheme.DARK
            }
        }
    }

    /**
     * Solar altitude in degrees at the given location and UTC instant. NOAA
     * low-precision formula (Astronomical Algorithms §25, Meeus): accurate to
     * a few arc-minutes, far better than the ±6° civil-twilight margin we
     * gate on. Treats UTC ≈ TT (the seconds-scale drift moves the sun
     * <0.04°, well below tolerance).
     */
    fun solarAltitudeDegrees(lat: Double, lng: Double, nowMillisUtc: Long): Double {
        val daysSinceJ2000 = (nowMillisUtc - J2000_EPOCH_MS).toDouble() / MS_PER_DAY

        val meanLongDeg = wrap360(280.460 + 0.9856474 * daysSinceJ2000)
        val meanAnomDeg = wrap360(357.528 + 0.9856003 * daysSinceJ2000)
        val gRad = meanAnomDeg * DEG_TO_RAD
        val eclipticLongDeg = meanLongDeg + 1.915 * sin(gRad) + 0.020 * sin(2.0 * gRad)
        val obliquityDeg = 23.439 - 0.0000004 * daysSinceJ2000

        val lambdaRad = eclipticLongDeg * DEG_TO_RAD
        val epsilonRad = obliquityDeg * DEG_TO_RAD
        val sinLambda = sin(lambdaRad)
        val cosLambda = cos(lambdaRad)
        val sinEps = sin(epsilonRad)
        val cosEps = cos(epsilonRad)

        val declRad = asin(sinEps * sinLambda)
        val raRad = atan2(cosEps * sinLambda, cosLambda)
        val raDeg = wrap360(raRad * RAD_TO_DEG)

        // Greenwich Mean Sidereal Time (degrees) → Local Sidereal Time → Hour angle.
        val gmstDeg = wrap360(280.46061837 + 360.98564736629 * daysSinceJ2000)
        val lstDeg = wrap360(gmstDeg + lng)
        val hourAngleRad = wrap180(lstDeg - raDeg) * DEG_TO_RAD

        val latRad = lat * DEG_TO_RAD
        val sinAlt = sin(latRad) * sin(declRad) + cos(latRad) * cos(declRad) * cos(hourAngleRad)
        return asin(sinAlt.coerceIn(-1.0, 1.0)) * RAD_TO_DEG
    }

    private const val J2000_EPOCH_MS = 946_728_000_000L
    private const val MS_PER_DAY = 86_400_000L
    private const val DEG_TO_RAD = PI / 180.0
    private const val RAD_TO_DEG = 180.0 / PI

    private fun wrap360(deg: Double): Double {
        val mod = deg % 360.0
        return if (mod < 0.0) mod + 360.0 else mod
    }

    private fun wrap180(deg: Double): Double {
        var x = wrap360(deg)
        if (x > 180.0) x -= 360.0
        return x
    }
}
