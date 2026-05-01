// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Foundation

/// Simple Kalman filter for GPS position and speed smoothing.
/// Filters latitude, longitude, and speed independently.
/// Bearing is passed through unfiltered (GPS bearing is already multi-fix derived).
///
/// Mutating value type — embed inside an actor or @MainActor class for safe
/// concurrent use.
public struct GpsFilter: Sendable {
    private let defaultAccuracy: Double
    private let minAccuracy: Double

    private var latEstimate = 0.0
    private var lngEstimate = 0.0
    private var speedEstimate = 0.0
    private var latVariance = Double.greatestFiniteMagnitude
    private var lngVariance = Double.greatestFiniteMagnitude
    private var speedVariance = Double.greatestFiniteMagnitude
    private var lastTimestamp: Int64 = 0
    private var initialized = false

    public init(defaultAccuracy: Double = 10.0, minAccuracy: Double = 1.0) {
        self.defaultAccuracy = defaultAccuracy
        self.minAccuracy = minAccuracy
    }

    public mutating func filter(_ raw: GpsPoint) -> GpsPoint {
        let accuracy = max(raw.accuracy ?? defaultAccuracy, minAccuracy)
        let measurementVariance = accuracy * accuracy

        if !initialized {
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

        // Prediction step: increase variance based on time elapsed and speed.
        let dt = Double(raw.timestamp - lastTimestamp) / 1000.0
        lastTimestamp = raw.timestamp

        if dt > 0 && dt < 30 {
            // Process noise scales with speed (faster = more expected position change).
            let speedMs = raw.speed / 3.6
            let processNoiseRaw = speedMs * dt
            let processNoise = processNoiseRaw * processNoiseRaw * 0.01
            let speedProcessNoise = 4.0 * dt

            latVariance += processNoise / (111_320.0 * 111_320.0)
            lngVariance += processNoise / (111_320.0 * 111_320.0)
            speedVariance += speedProcessNoise
        } else {
            // Large gap — reset to measurement.
            latEstimate = raw.lat
            lngEstimate = raw.lng
            speedEstimate = raw.speed
            latVariance = measurementVariance
            lngVariance = measurementVariance
            speedVariance = measurementVariance
            return raw.with(lat: latEstimate, lng: lngEstimate, speed: speedEstimate)
        }

        // Update step: blend prediction with measurement.
        let latMeasVar = measurementVariance / (111_320.0 * 111_320.0)
        let lngMeasVar = measurementVariance / (111_320.0 * 111_320.0)
        let speedMeasVar = accuracy * 0.5

        let latGain = latVariance / (latVariance + latMeasVar)
        let lngGain = lngVariance / (lngVariance + lngMeasVar)
        let speedGain = speedVariance / (speedVariance + speedMeasVar)

        latEstimate += latGain * (raw.lat - latEstimate)
        lngEstimate += lngGain * (raw.lng - lngEstimate)
        speedEstimate += speedGain * (raw.speed - speedEstimate)
        speedEstimate = max(speedEstimate, 0.0)

        latVariance *= (1.0 - latGain)
        lngVariance *= (1.0 - lngGain)
        speedVariance *= (1.0 - speedGain)

        return raw.with(lat: latEstimate, lng: lngEstimate, speed: speedEstimate)
    }

    public mutating func reset() {
        initialized = false
        latEstimate = 0
        lngEstimate = 0
        speedEstimate = 0
        latVariance = .greatestFiniteMagnitude
        lngVariance = .greatestFiniteMagnitude
        speedVariance = .greatestFiniteMagnitude
        lastTimestamp = 0
    }
}
