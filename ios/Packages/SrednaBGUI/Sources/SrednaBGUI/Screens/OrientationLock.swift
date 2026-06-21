// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGUI

import SwiftUI
#if os(iOS)
import UIKit
#endif

/// Per-screen interface-orientation preference. `RootView` drives this off the
/// active tab so Home and Settings stay portrait (they were never laid out for
/// landscape) while the Map tab is free to rotate.
public enum AppScreenOrientation {
    /// Portrait only — Home, Settings, About.
    case portrait
    /// Portrait + both landscape — the Map tab.
    case free
}

/// App-wide supported-orientation gate. In a pure-SwiftUI app the allowed set
/// is resolved by the app delegate's
/// `application(_:supportedInterfaceOrientationsFor:)`; the app-shell's
/// `AppDelegate` returns `OrientationLock.shared.mask`, and `RootView` updates
/// that mask (and actively rotates) on every tab change via ``apply(_:)``.
///
/// iOS-only behavior; the type exists on macOS so the SrednaBGUI module still
/// compiles for `swift test`, where ``apply(_:)`` is a no-op. Main-actor
/// isolated — the mask is read from the (main-actor) `UIApplicationDelegate`
/// callback and mutated from `RootView`, both on the main thread.
@MainActor
public final class OrientationLock {

    public static let shared = OrientationLock()

    private init() {}

    #if os(iOS)
    /// The mask the `AppDelegate` hands back to UIKit. Defaults to portrait so
    /// the app comes up portrait before `RootView`'s first `apply(_:)` runs.
    public var mask: UIInterfaceOrientationMask = .portrait

    /// Narrows (or widens) the allowed orientations to match `orientation` and
    /// forces the foreground window to re-evaluate immediately — so leaving the
    /// Map tab while held in landscape snaps back to portrait, and entering it
    /// lets the device rotate.
    public func apply(_ orientation: AppScreenOrientation) {
        let newMask: UIInterfaceOrientationMask =
            orientation == .free ? .allButUpsideDown : .portrait
        mask = newMask

        guard let scene = UIApplication.shared.connectedScenes
            .compactMap({ $0 as? UIWindowScene })
            .first(where: { $0.activationState == .foregroundActive })
        else { return }

        scene.requestGeometryUpdate(.iOS(interfaceOrientations: newMask))
        scene.keyWindow?.rootViewController?
            .setNeedsUpdateOfSupportedInterfaceOrientations()
    }
    #else
    /// No-op on non-iOS (macOS `swift test`).
    public func apply(_ orientation: AppScreenOrientation) {}
    #endif
}
