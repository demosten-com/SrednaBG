// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / core

package com.demosten.srednabg.core

/**
 * Simple Kalman filter for GPS position and speed smoothing.
 * Filters latitude, longitude, and speed independently.
 * Bearing is passed through unfiltered (GPS bearing is already multi-fix derived).
 */
class GpsFilter(
    private val defaultAccuracy: Double = 10.0,
    private val minAccuracy: Double = 1.0,
) {
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

        if (!initialized) {
            latEstimate = raw.lat
            lngEstimate = raw.lng
            speedEstimate = raw.speed
            latVariance = measurementVariance
            lngVariance = measurementVariance
            speedVariance = measurementVariance
            lastTimestamp = raw.timestamp
            initialized = true
            return raw
        }

        // Prediction step: increase variance based on time elapsed and speed
        val dt = (raw.timestamp - lastTimestamp) / 1000.0
        lastTimestamp = raw.timestamp

        if (dt > 0 && dt < 30) {
            // Process noise scales with speed (faster = more expected position change)
            // At 140 km/h (~39 m/s), process noise ~39m per second
            val speedMs = raw.speed / 3.6
            val processNoise = (speedMs * dt).let { it * it * 0.01 } // conservative
            val speedProcessNoise = 4.0 * dt // speed can change ~4 km/h per second

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
            speedVariance = measurementVariance
            return raw.copy(lat = latEstimate, lng = lngEstimate, speed = speedEstimate)
        }

        // Update step: blend prediction with measurement
        val latMeasVar = measurementVariance / (111_320.0 * 111_320.0)
        val lngMeasVar = measurementVariance / (111_320.0 * 111_320.0)
        val speedMeasVar = accuracy * 0.5 // speed accuracy is roughly half position accuracy

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
