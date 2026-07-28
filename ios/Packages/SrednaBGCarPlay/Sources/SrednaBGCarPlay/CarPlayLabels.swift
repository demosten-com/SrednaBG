// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCarPlay

import Foundation

/// Bag of pre-resolved strings the CarPlay overlay + nav session need.
/// CarPlay doesn't depend on `SrednaBGUI` (which owns `L10n`) so the app
/// shell resolves strings via `L10n` and hands them in through
/// `CarPlayServiceBundle.labelsProvider`. The closure is re-invoked on
/// each observation tick, so language switches from the phone settings
/// screen show up in CarPlay without a re-connect.
public struct CarPlayLabels: Sendable, Equatable {
    public let overLimit: String
    public let withinLimit: String
    public let nowSpeedFormat: String    // "Now %@ km/h" — %@ carries "--" or the integer
    public let currentSpeedLabel: String // "current" subtitle under the small speed
    public let avgSpeedLabel: String     // "avg" subtitle under the hero speed
    public let remaining: String         // "remaining" subtitle under the distance
    public let speedLimit: String        // "limit" subtitle under the badge
    public let finalAvgSpeedFormat: String // "final %@ km/h" (Exiting state)
    public let zoneCompleteTitle: String  // short title shown when traversal ends
    public let trackingOutsideTitle: String
    public let notTrackingTitle: String
    public let tapToStartHint: String
    /// Short form for a zone we're in but didn't see entered. Must clear the
    /// CarPlay/AA glyph-size floors, so keep it to two or three words.
    public let notMeasuredTitle: String

    public init(
        overLimit: String,
        withinLimit: String,
        nowSpeedFormat: String,
        currentSpeedLabel: String,
        avgSpeedLabel: String,
        remaining: String,
        speedLimit: String,
        finalAvgSpeedFormat: String,
        zoneCompleteTitle: String,
        trackingOutsideTitle: String,
        notTrackingTitle: String,
        tapToStartHint: String,
        notMeasuredTitle: String
    ) {
        self.overLimit = overLimit
        self.withinLimit = withinLimit
        self.nowSpeedFormat = nowSpeedFormat
        self.currentSpeedLabel = currentSpeedLabel
        self.avgSpeedLabel = avgSpeedLabel
        self.remaining = remaining
        self.speedLimit = speedLimit
        self.finalAvgSpeedFormat = finalAvgSpeedFormat
        self.zoneCompleteTitle = zoneCompleteTitle
        self.trackingOutsideTitle = trackingOutsideTitle
        self.notTrackingTitle = notTrackingTitle
        self.tapToStartHint = tapToStartHint
        self.notMeasuredTitle = notMeasuredTitle
    }
}
