// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCarPlay

#if canImport(CarPlay)
import CarPlay
import UIKit

/// iOS loads this class via `NSClassFromString` using the bare ObjC name
/// in `Info.plist` (`UISceneDelegateClassName = CarPlaySceneDelegate`);
/// the explicit `@objc(CarPlaySceneDelegate)` keeps that name stable
/// regardless of Swift module.
@objc(CarPlaySceneDelegate)
@MainActor
public final class CarPlaySceneDelegate: UIResponder, CPTemplateApplicationSceneDelegate {

    private var coordinator: CarPlaySceneCoordinator?

    public func templateApplicationScene(
        _ templateApplicationScene: CPTemplateApplicationScene,
        didConnect interfaceController: CPInterfaceController,
        to window: CPWindow
    ) {
        guard let bundle = CarPlayModule.sharedBundle else {
            // The app shell hasn't handed services in yet — either the
            // process is coming up cold and `SrednaBGApp.init` hasn't
            // run `CarPlayModule.configure` (can't happen in practice;
            // scene connect is strictly after app init), or someone
            // disabled the hook. Leave the window empty; iOS retries
            // the connect on the next scene activation.
            return
        }
        let coord = CarPlaySceneCoordinator(
            interfaceController: interfaceController,
            window: window,
            bundle: bundle
        )
        self.coordinator = coord
        coord.start()
    }

    public func templateApplicationScene(
        _ templateApplicationScene: CPTemplateApplicationScene,
        didDisconnect interfaceController: CPInterfaceController,
        from window: CPWindow
    ) {
        coordinator?.stop()
        coordinator = nil
    }
}
#endif
