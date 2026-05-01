// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGMapCore

import Foundation

/// Holds the last observed bearing and refuses to update while the user is
/// stopped. Mirrors Android's `BEARING_MIN_SPEED_KMH = 5.0` in
/// `ZoneMapScreen.kt` — GPS bearing is noisy at low speeds and makes the
/// user-arrow spin at traffic lights.
public struct BearingDamper: Sendable, Equatable {

    public static let minSpeedKmh: Double = 5.0

    public private(set) var effectiveBearing: Double

    public init(initial: Double = 0) {
        self.effectiveBearing = Self.normalize(initial)
    }

    /// Returns the new effective bearing. Updates in place when
    /// `speedKmh > minSpeedKmh`; otherwise holds the previous value.
    @discardableResult
    public mutating func update(speedKmh: Double, bearingDegrees: Double) -> Double {
        if speedKmh > Self.minSpeedKmh {
            effectiveBearing = Self.normalize(bearingDegrees)
        }
        return effectiveBearing
    }

    public static func normalize(_ bearing: Double) -> Double {
        let mod = bearing.truncatingRemainder(dividingBy: 360)
        return mod < 0 ? mod + 360 : mod
    }
}
