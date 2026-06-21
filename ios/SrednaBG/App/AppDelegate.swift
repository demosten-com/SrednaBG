// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBG

import UIKit
import SrednaBGUI

/// Minimal app delegate whose only job is to expose the per-screen
/// interface-orientation mask to UIKit. A pure-SwiftUI app resolves the allowed
/// orientations through this callback; `RootView` drives `OrientationLock` off
/// the active tab so Home + Settings stay portrait while the Map tab rotates.
/// Wired into `SrednaBGApp` via `@UIApplicationDelegateAdaptor`.
final class AppDelegate: NSObject, UIApplicationDelegate {

    func application(
        _ application: UIApplication,
        supportedInterfaceOrientationsFor window: UIWindow?
    ) -> UIInterfaceOrientationMask {
        OrientationLock.shared.mask
    }
}
