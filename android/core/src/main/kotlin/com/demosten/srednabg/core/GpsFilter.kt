// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

/**
 * Simple Kalman filter for GPS position and speed smoothing.
 * Filters latitude, longitude, and speed independently.
 * Bearing is passed through unfiltered (GPS bearing is already multi-fix derived).
 *
 * Holds mutable filter state across [filter] calls with no internal
 * synchronization — it is **not** thread-safe and must be confined to a single
 * thread (in the app, the `LocationTrackingService` GPS-consumer coroutine). The
 * Swift port documents the same contract as a mutating value type embedded inside
 * an actor / `@MainActor` class.
 */
class GpsFilter(
    private val defaultAccuracy: Double = 10.0,
    private val minAccuracy: Double = 1.0,
) {
    private companion object {
        // Speed-filter noise, all in (km/h)² so the Kalman variances stay
        // dimensionally consistent (the position filter works in degrees²).
        //
        // Measurement std (km/h) ≈ positional accuracy (m) × this factor: a
        // coarser fix yields a noisier Doppler/derived speed. Squared into a
        // variance before use.
        const val SPEED_MEAS_STD_PER_ACCURACY = 0.5
        // Floor so a pinpoint fix (accuracy ~1 m) still carries a realistic
        // ~1 km/h speed-measurement std rather than collapsing the filter to a
        // passthrough.
        const val MIN_SPEED_MEAS_STD_KMH = 1.0
        // Process noise (km/h)²/s — how much real speed can drift between fixes.
        // A few km/h per second covers normal accel/brake; deliberately below
        // the legacy 4.0 so the filter actually smooths instead of trusting each
        // raw sample ~70%.
        const val SPEED_PROCESS_NOISE_PER_S = 2.0
    }

    private var latEstimate = 0.0
    private var lngEstimate = 0.0
    private var speedEstimate = 0.0
    private var latVariance = Double.MAX_VALUE
    private var lngVariance = Double.MAX_VALUE
    private var speedVariance = Double.MAX_VALUE
    private var lastTimestamp = 0L
    private var initialized = false

    fun filter(raw: GpsPoint): GpsPoint {
        val accuracy = (raw.accuracy ?: defaultAccuracy).coerceAtLeast(minAccuracy)
        val measurementVariance = accuracy * accuracy
        // Speed measurement variance in (km/h)² — see companion notes. Kept
        // separate from the positional measurementVariance (m²) so the speed
        // channel doesn't inherit metre-squared units.
        val speedMeasStd =
            (accuracy * SPEED_MEAS_STD_PER_ACCURACY).coerceAtLeast(MIN_SPEED_MEAS_STD_KMH)
        val speedMeasVar = speedMeasStd * speedMeasStd

        if (!initialized) {
            latEstimate = raw.lat
            lngEstimate = raw.lng
            speedEstimate = raw.speed
            latVariance = measurementVariance
            lngVariance = measurementVariance
            speedVariance = speedMeasVar
            lastTimestamp = raw.timestamp
            initialized = true
            return raw
        }

        // Prediction step: increase variance based on time elapsed and speed
        val dt = (raw.timestamp - lastTimestamp) / 1000.0
        lastTimestamp = raw.timestamp

        if (dt >= 0 && dt < 30) {
            // dt == 0 (two fixes share a timestamp — FLP batching, or a QA feed
            // with an overridden time_ms) makes every process-noise term below
            // zero, so this becomes a pure measurement-blend with no prediction —
            // the right thing. Only a backwards (dt < 0) or large (dt >= 30) gap
            // falls to the reset branch. Process noise scales with speed (faster =
            // more expected position change); at 140 km/h (~39 m/s) it's ~39 m/s.
            val speedMs = raw.speed / 3.6
            val processNoise = (speedMs * dt).let { it * it * 0.01 } // conservative
            val speedProcessNoise = SPEED_PROCESS_NOISE_PER_S * dt // (km/h)²/s

            latVariance += processNoise / (111_320.0 * 111_320.0) // convert meters to degrees
            lngVariance += processNoise / (111_320.0 * 111_320.0)
            speedVariance += speedProcessNoise
        } else {
            // Large gap — reset to measurement
            latEstimate = raw.lat
            lngEstimate = raw.lng
            speedEstimate = raw.speed
            latVariance = measurementVariance
            lngVariance = measurementVariance
            speedVariance = speedMeasVar
            return raw.copy(lat = latEstimate, lng = lngEstimate, speed = speedEstimate)
        }

        // Update step: blend prediction with measurement
        val latMeasVar = measurementVariance / (111_320.0 * 111_320.0)
        val lngMeasVar = measurementVariance / (111_320.0 * 111_320.0)
        // speedMeasVar computed above, in (km/h)².

        val latGain = latVariance / (latVariance + latMeasVar)
        val lngGain = lngVariance / (lngVariance + lngMeasVar)
        val speedGain = speedVariance / (speedVariance + speedMeasVar)

        latEstimate += latGain * (raw.lat - latEstimate)
        lngEstimate += lngGain * (raw.lng - lngEstimate)
        speedEstimate += speedGain * (raw.speed - speedEstimate)
        speedEstimate = speedEstimate.coerceAtLeast(0.0)

        latVariance *= (1.0 - latGain)
        lngVariance *= (1.0 - lngGain)
        speedVariance *= (1.0 - speedGain)

        return raw.copy(
            lat = latEstimate,
            lng = lngEstimate,
            speed = speedEstimate,
        )
    }

    fun reset() {
        initialized = false
        latEstimate = 0.0
        lngEstimate = 0.0
        speedEstimate = 0.0
        latVariance = Double.MAX_VALUE
        lngVariance = Double.MAX_VALUE
        speedVariance = Double.MAX_VALUE
        lastTimestamp = 0L
    }
}
