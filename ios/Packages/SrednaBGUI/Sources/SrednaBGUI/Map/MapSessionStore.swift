// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGUI

import Foundation
import Observation

/// Per-process state for the Map tab that has to outlive a SwiftUI tab
/// switch. `TabView` tears down the off-screen tab's view tree, so anything
/// kept as `@State` inside `ZoneMapScreen` is gone the moment the user
/// taps Home. Hoisting the camera + follow state up to a `RootView`-owned
/// `@State` instance of this `@Observable` class is what lets returning to
/// the Map tab feel like the user never left.
///
/// Lives in memory only — process death legitimately resets to the default
/// Bulgaria-wide view, mirroring the Android `ZoneMapViewModel.cameraSnapshot`
/// scope.
@Observable
@MainActor
public final class MapSessionStore {

    public var cameraSnapshot: MapCameraSnapshot?
    public var isFollowing: Bool

    /// The History-detail "Show on map" request, if any. The Map tab honors it
    /// only while tracking is off; `RootView` clears it the moment tracking
    /// starts so live tracking and the highlight never drive the map together.
    public private(set) var highlight: MapHighlight?

    /// Which highlight request the camera has already fitted — kept here (not
    /// in `ZoneMapScreen` `@State`) so a tab round-trip doesn't re-fit, while a
    /// fresh "Show on map" press (new `requestId`) always does.
    public var lastFittedHighlightRequestId: UInt64?

    private var nextHighlightRequestId: UInt64 = 0

    public init(isFollowing: Bool = true) {
        self.isFollowing = isFollowing
    }

    public func requestHighlight(zoneId: String, isOverLimit: Bool) {
        nextHighlightRequestId += 1
        highlight = MapHighlight(
            zoneId: zoneId,
            isOverLimit: isOverLimit,
            requestId: nextHighlightRequestId
        )
    }

    public func clearHighlight() {
        highlight = nil
    }
}

/// A History-detail "Show on map" request: highlight this zone on the Map tab
/// with the trip's verdict color (green within limit, red over).
public struct MapHighlight: Equatable, Sendable {
    public let zoneId: String
    public let isOverLimit: Bool
    public let requestId: UInt64
}

public struct MapCameraSnapshot: Equatable, Sendable {
    public let lat: Double
    public let lng: Double
    public let zoom: Double
    public let bearing: Double
    public let pitch: Double

    public init(lat: Double, lng: Double, zoom: Double, bearing: Double, pitch: Double) {
        self.lat = lat
        self.lng = lng
        self.zoom = zoom
        self.bearing = bearing
        self.pitch = pitch
    }
}
