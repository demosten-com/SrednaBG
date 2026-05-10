// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGUI

import SwiftUI
#if os(iOS)
import UIKit
#endif

/// Toggles the system idle timer based on a Boolean. Applied at the TabView
/// root by `RootView` so the screen stays awake on every tab while tracking is
/// active.
///
/// `UIApplication.isIdleTimerDisabled` resets to `false` whenever the app is
/// backgrounded, so observing only the `isActive` value would silently
/// regress on the first lock/unlock cycle. The `scenePhase` handler below
/// re-asserts the current value when the app returns to `.active`.
struct KeepScreenAwakeModifier: ViewModifier {

    let isActive: Bool

    @Environment(\.scenePhase) private var scenePhase

    func body(content: Content) -> some View {
        #if os(iOS)
        content
            .onChange(of: isActive, initial: true) { _, newValue in
                UIApplication.shared.isIdleTimerDisabled = newValue
            }
            .onChange(of: scenePhase) { _, newPhase in
                if newPhase == .active {
                    UIApplication.shared.isIdleTimerDisabled = isActive
                }
            }
            .onDisappear {
                UIApplication.shared.isIdleTimerDisabled = false
            }
        #else
        content
        #endif
    }
}

extension View {

    /// Keeps the device awake while `isActive` is `true`. iOS-only behavior;
    /// no-op on macOS so the SrednaBGUI module still compiles for `swift test`.
    func keepScreenAwake(while isActive: Bool) -> some View {
        modifier(KeepScreenAwakeModifier(isActive: isActive))
    }
}
