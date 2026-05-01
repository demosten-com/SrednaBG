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

    public init(isFollowing: Bool = true) {
        self.isFollowing = isFollowing
    }
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
