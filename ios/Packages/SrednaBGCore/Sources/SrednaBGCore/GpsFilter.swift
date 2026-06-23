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
    // Speed-filter noise, all in (km/h)² so the Kalman variances stay
    // dimensionally consistent (the position filter works in degrees²).
    //
    // Measurement std (km/h) ≈ positional accuracy (m) × this factor: a coarser
    // fix yields a noisier Doppler/derived speed. Squared into a variance.
    private static let speedMeasStdPerAccuracy = 0.5
    // Floor so a pinpoint fix (accuracy ~1 m) still carries a realistic ~1 km/h
    // speed-measurement std rather than collapsing the filter to a passthrough.
    private static let minSpeedMeasStdKmh = 1.0
    // Process noise (km/h)²/s — how much real speed can drift between fixes. A
    // few km/h per second covers normal accel/brake; deliberately below the
    // legacy 4.0 so the filter actually smooths instead of trusting each raw
    // sample ~70%.
    private static let speedProcessNoisePerS = 2.0

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
        // Speed measurement variance in (km/h)² — see the static notes. Kept
        // separate from the positional measurementVariance (m²) so the speed
        // channel doesn't inherit metre-squared units.
        let speedMeasStd = max(
            accuracy * Self.speedMeasStdPerAccuracy,
            Self.minSpeedMeasStdKmh
        )
        let speedMeasVar = speedMeasStd * speedMeasStd

        if !initialized {
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

        // Prediction step: increase variance based on time elapsed and speed.
        let dt = Double(raw.timestamp - lastTimestamp) / 1000.0
        lastTimestamp = raw.timestamp

        if dt >= 0 && dt < 30 {
            // dt == 0 (two fixes share a timestamp — FLP batching, or a QA feed
            // with an overridden time_ms) makes every process-noise term below
            // zero, so this becomes a pure measurement-blend with no prediction —
            // the right thing. Only a backwards (dt < 0) or large (dt >= 30) gap
            // falls to the reset branch. Process noise scales with speed.
            let speedMs = raw.speed / 3.6
            let processNoiseRaw = speedMs * dt
            let processNoise = processNoiseRaw * processNoiseRaw * 0.01
            let speedProcessNoise = Self.speedProcessNoisePerS * dt // (km/h)²/s

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
            speedVariance = speedMeasVar
            return raw.with(lat: latEstimate, lng: lngEstimate, speed: speedEstimate)
        }

        // Update step: blend prediction with measurement.
        let latMeasVar = measurementVariance / (111_320.0 * 111_320.0)
        let lngMeasVar = measurementVariance / (111_320.0 * 111_320.0)
        // speedMeasVar computed above, in (km/h)².

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
