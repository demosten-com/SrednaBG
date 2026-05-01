// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCarPlay

import Foundation
import SrednaBGCore
import SrednaBGData
import SrednaBGTracking

/// Dependency bundle the SwiftUI app shell hands into the CarPlay module
/// before iOS instantiates `CarPlaySceneDelegate`. Because iOS builds
/// scene delegates by class name (`UISceneDelegateClassName` in
/// Info.plist), the delegate can't take constructor arguments — services
/// are handed in through a module-level registry instead.
@MainActor
public struct CarPlayServiceBundle {
    public let tracking: ZoneTrackingService
    public let settings: SettingsStore
    /// Re-invoked on every observation tick so a language switch flows
    /// through without a scene re-connect.
    public let labelsProvider: @MainActor () -> CarPlayLabels
    /// Resolves the offline-map MapLibre style URL. Shared with the phone
    /// map tab — `AppContainer.mapStyleURL()` owns the single
    /// `LocalTileServer` + `MBTilesReader` instance.
    public let mapStyleURLProvider: @Sendable () async -> URL?

    public init(
        tracking: ZoneTrackingService,
        settings: SettingsStore,
        labelsProvider: @escaping @MainActor () -> CarPlayLabels,
        mapStyleURLProvider: @escaping @Sendable () async -> URL?
    ) {
        self.tracking = tracking
        self.settings = settings
        self.labelsProvider = labelsProvider
        self.mapStyleURLProvider = mapStyleURLProvider
    }
}

/// Module-level registry so `CarPlaySceneDelegate` — which iOS constructs
/// via NSClassFromString — can reach the live services. The app shell
/// must call `configure(_:)` during `init()` before any CarPlay scene
/// can connect; connecting without a configured bundle fails silently
/// (the scene loads an empty map template, not a crash).
public enum CarPlayModule {

    public static func configure(_ bundle: CarPlayServiceBundle) {
        MainActor.assumeIsolated {
            Self.storage = bundle
            // Anchor `CarPlaySceneDelegate` so the SwiftPM static library
            // doesn't dead-strip it. iOS resolves the class via
            // `NSClassFromString` from `Info.plist`, but `@objc(...)`
            // only helps if the class is still in the linked binary —
            // and nothing in Swift code references the type directly,
            // so without this `_ = ...` the launcher silently skips us.
            #if canImport(CarPlay)
            _ = CarPlaySceneDelegate.self
            #endif
        }
    }

    @MainActor
    public static var sharedBundle: CarPlayServiceBundle? {
        Self.storage
    }

    /// Storage is written only on the main actor via `configure`; the
    /// `nonisolated(unsafe)` wart lets `CarPlaySceneDelegate`'s init (which
    /// iOS invokes on the main thread before we can adopt `@MainActor`)
    /// read without a hop. The invariant is enforced by `configure` being
    /// the only mutator and `MainActor.assumeIsolated` gating it.
    nonisolated(unsafe) private static var storage: CarPlayServiceBundle?
}
