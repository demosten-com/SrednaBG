// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGUI

#if os(iOS)
import Foundation
import SwiftUI
import UIKit
@preconcurrency import MapLibre
import SrednaBGCore
import SrednaBGData
import SrednaBGTracking
import SrednaBGMapCore

/// SwiftUI wrapper around `MLNMapView`. Owns the live zone polyline layers,
/// user-arrow symbol, and camera-follow logic. Matches the Android phone
/// UI's `ZoneMapScreen.kt` feature set.
@MainActor
struct MapLibreView: UIViewRepresentable {

    let styleURL: URL
    let zones: [Zone]
    let activeZoneId: String?
    let currentPosition: GpsPoint?
    let displayPosition: GpsPoint?
    let zoneState: ZoneState
    let headingUp: Bool
    let mapSession: MapSessionStore
    let zoomOverride: Double?
    @Binding var pendingCommand: MapCommand?
    @Binding var styleLoadFailed: Bool
    @Binding var isMapReady: Bool

    enum MapCommand: Sendable, Equatable {
        case zoomIn
        case zoomOut
        case recenter
        case zoomTo(Double)
    }

    /// Default zoom for the follow camera when no per-shot override is set.
    /// Mirrors Android's `USER_FOLLOW_ZOOM` constant in `ZoneMapScreen.kt`.
    static let userFollowZoom: Double = 14.0

    func makeCoordinator() -> Coordinator {
        Coordinator(parent: self)
    }

    func makeUIView(context: Context) -> MLNMapView {
        let mapView = MLNMapView(frame: .zero, styleURL: styleURL)
        mapView.delegate = context.coordinator
        mapView.compassView.isHidden = false
        // Anchor the compass at bottom-right above the controls toolbar so it
        // doesn't sit under the in-zone StatusChip when heading-up follow
        // rotates the map (chip overlays the default top-right corner).
        mapView.compassViewPosition = .bottomRight
        mapView.compassViewMargins = CGPoint(x: 8, y: 76)
        mapView.logoView.isHidden = false
        mapView.attributionButton.isHidden = false
        mapView.showsUserLocation = false
        // MapLibre reads the enclosing UIViewController's (deprecated)
        // `automaticallyAdjustsScrollViewInsets` unless we opt out here —
        // setting this silences the console warning and lets SwiftUI own
        // safe-area insets.
        mapView.automaticallyAdjustsContentInset = false
        if let snap = mapSession.cameraSnapshot {
            // Restore the previous tab session's camera so a Home → Map
            // round-trip lands the user back where they were instead of
            // resetting to the Bulgaria-wide default.
            mapView.setCenter(
                CLLocationCoordinate2D(latitude: snap.lat, longitude: snap.lng),
                zoomLevel: snap.zoom,
                direction: snap.bearing,
                animated: false
            )
            context.coordinator.didRestoreCameraSnapshot = true
            // Treat a restored snapshot as already-followed-once so the next
            // GPS update preserves the user's saved zoom instead of yanking
            // it to `userFollowZoom`.
            context.coordinator.didFollowOnce = true
        } else {
            // First Map mount this process: center over Bulgaria until the
            // first GPS point or active-zone fit takes over.
            let bulgariaCenter = CLLocationCoordinate2D(latitude: 42.7339, longitude: 25.4858)
            mapView.setCenter(bulgariaCenter, zoomLevel: 9, animated: false)
        }
        context.coordinator.mapView = mapView
        return mapView
    }

    func updateUIView(_ uiView: MLNMapView, context: Context) {
        let coord = context.coordinator
        coord.parent = self

        if uiView.styleURL != styleURL {
            coord.layersInstalled = false
            // Style is being swapped — retract the ready flag so the loading
            // overlay reappears until the new style finishes rendering.
            if isMapReady {
                DispatchQueue.main.async { self.isMapReady = false }
            }
            uiView.styleURL = styleURL
            return
        }

        guard let style = uiView.style, coord.layersInstalled else {
            // Style still loading; the delegate's `didFinishLoading` will
            // re-enter this apply path after layers are installed.
            return
        }

        if coord.lastZoneIds != zones.map(\.id) {
            MapLayers.applyZones(zones, to: style)
            coord.lastZoneIds = zones.map(\.id)
        }

        let activeZone = zones.first(where: { $0.id == activeZoneId })
        if coord.lastActiveZoneId != activeZoneId {
            MapLayers.applyEndpoints(for: activeZone, to: style)
            coord.lastActiveZoneId = activeZoneId
            // Fit-on-entry only when the user isn't actively following AND
            // we didn't just restore a saved camera (in which case the
            // restored zoom + pan must win).
            if let zone = activeZone, !mapSession.isFollowing, !coord.didRestoreCameraSnapshot,
               zoomOverride == nil {
                fit(uiView: uiView, to: zone)
            }
        }

        MapLayers.applyActiveZone(
            activeZoneId,
            color: activeZoneColor(),
            to: style
        )

        if let point = currentPosition {
            coord.damper.update(speedKmh: point.speed, bearingDegrees: point.bearing)
        }
        MapLayers.applyUser(
            displayPosition ?? currentPosition,
            bearing: coord.damper.effectiveBearing,
            to: style
        )

        if mapSession.isFollowing, let position = displayPosition ?? currentPosition {
            applyFollowCamera(uiView: uiView, position: position, coordinator: coord)
        }

        if let command = pendingCommand {
            apply(command: command, to: uiView, coordinator: coord)
            // Using `DispatchQueue.main.async` here keeps the binding reset
            // out of this view-update pass — SwiftUI complains if we mutate
            // state synchronously during `updateUIView`.
            DispatchQueue.main.async {
                self.pendingCommand = nil
            }
        }
    }

    // MARK: - Helpers

    private func activeZoneColor() -> UIColor {
        switch zoneState {
        case .inZone(let inZone):
            return statusUIColor(zoneStatusColor(state: inZone, currentSpeedKmh: currentPosition?.speed))
        case .exiting, .outside:
            return MapLayers.activeRedLineColor
        }
    }

    private func fit(uiView: MLNMapView, to zone: Zone) {
        guard zone.centerline.count >= 2 else { return }
        let lats = zone.centerline.map { $0[0] }
        let lngs = zone.centerline.map { $0[1] }
        guard let minLat = lats.min(), let maxLat = lats.max(),
              let minLng = lngs.min(), let maxLng = lngs.max()
        else { return }
        let bounds = MLNCoordinateBounds(
            sw: CLLocationCoordinate2D(latitude: minLat, longitude: minLng),
            ne: CLLocationCoordinate2D(latitude: maxLat, longitude: maxLng)
        )
        uiView.setVisibleCoordinateBounds(
            bounds,
            edgePadding: UIEdgeInsets(top: 128, left: 64, bottom: 128, right: 64),
            animated: true
        )
    }

    private func applyFollowCamera(uiView: MLNMapView, position: GpsPoint, coordinator: Coordinator) {
        let coord = CLLocationCoordinate2D(latitude: position.lat, longitude: position.lng)
        let effectiveBearing = coordinator.damper.effectiveBearing
        // Mirror Android's follow-camera zoom logic (ZoneMapScreen.kt:381/396):
        //   override > preserve-current > USER_FOLLOW_ZOOM. We also force a
        //   one-shot bump to USER_FOLLOW_ZOOM the first time we follow without
        //   an override — the initial mount centers Bulgaria-wide at zoom 9 to
        //   render the empty-state, which would otherwise stick across every
        //   follow frame and leave the screenshots / first-launch map zoomed
        //   way out.
        let targetZoom: Double
        if let override = zoomOverride {
            targetZoom = override
        } else if !coordinator.didFollowOnce {
            targetZoom = Self.userFollowZoom
        } else {
            targetZoom = uiView.zoomLevel
        }
        coordinator.didFollowOnce = true
        let bearing: CLLocationDirection = headingUp ? effectiveBearing : 0
        coordinator.programmaticCameraChange = true
        // `setCenter(_:zoomLevel:direction:animated:)` writes the target zoom
        // directly. `MLNMapCamera(altitude:)` would be vulnerable to mid-animation
        // altitude reads — exactly the race that caused the override to bleed
        // back to the pre-zoom value on every subsequent GPS update.
        uiView.setCenter(coord, zoomLevel: targetZoom, direction: bearing, animated: true)
    }

    private func apply(command: MapCommand, to uiView: MLNMapView, coordinator: Coordinator) {
        coordinator.programmaticCameraChange = true
        switch command {
        case .zoomIn:
            uiView.setZoomLevel(uiView.zoomLevel + 1, animated: true)
        case .zoomOut:
            uiView.setZoomLevel(max(uiView.zoomLevel - 1, uiView.minimumZoomLevel), animated: true)
        case .recenter:
            if let position = displayPosition ?? currentPosition {
                applyFollowCamera(uiView: uiView, position: position, coordinator: coordinator)
            }
        case .zoomTo(let level):
            uiView.setZoomLevel(level, animated: true)
        }
    }

    // MARK: - Coordinator

    /// Non-isolated delegate. Pairing `@MainActor` with `@preconcurrency
    /// MLNMapViewDelegate` made the Swift runtime synthesize a dispatch_sync
    /// hop into the main actor on every delegate callback — which trips
    /// "Potential Structural Swift Concurrency Issue: unsafeForcedSync
    /// called from Swift Concurrent context." whenever the call stack
    /// passes through a Swift cooperative thread. MapLibre delegate
    /// methods are documented as main-thread, so we hop in explicitly via
    /// `MainActor.assumeIsolated` inside each method instead — that's a
    /// fast precondition check, not a sync wait.
    ///
    /// `@unchecked Sendable` is safe because every stored property is
    /// `@MainActor`-isolated; the class can be referenced from any thread
    /// (MapLibre holds the delegate strongly from its render thread) but
    /// state can only be mutated through the main actor.
    final class Coordinator: NSObject, MLNMapViewDelegate, @unchecked Sendable {
        @MainActor var parent: MapLibreView
        @MainActor weak var mapView: MLNMapView?
        @MainActor var layersInstalled: Bool = false
        @MainActor var lastZoneIds: [String] = []
        @MainActor var lastActiveZoneId: String?
        @MainActor var damper = BearingDamper()
        /// Set to `true` right before any programmatic camera change. The
        /// `regionWillChange` delegate callback consults this to avoid
        /// misclassifying our own camera pushes as user gestures.
        @MainActor var programmaticCameraChange: Bool = false
        /// Flipped on in `makeUIView` whenever a saved snapshot was applied,
        /// so the first `didFinishLoading` / `updateUIView` pass doesn't
        /// auto-fit the active zone over the restored camera.
        @MainActor var didRestoreCameraSnapshot: Bool = false
        /// `false` until `applyFollowCamera` has run at least once. On the
        /// first follow we bump the camera from the Bulgaria-wide seed zoom
        /// (9, set by `makeUIView`) to `userFollowZoom` (14); after that we
        /// preserve whatever zoom the user / override / pinch-gesture set.
        @MainActor var didFollowOnce: Bool = false

        @MainActor
        init(parent: MapLibreView) {
            self.parent = parent
        }

        func mapViewDidFailLoadingMap(_ mapView: MLNMapView, withError error: any Error) {
            NSLog("SrednaBG MapLibre: style load failed — \(error)")
            MainActor.assumeIsolated {
                self.parent.styleLoadFailed = true
                self.parent.isMapReady = false
            }
        }

        // MapLibre iOS needs these optional delegate methods registered on
        // the delegate object for the render path to flush consistently.
        // When they're absent, style loads succeed, tiles are fetched, but
        // no vector features paint — only the style background color.
        // Implementing them (even as trivial flags) unblocks rendering.
        func mapViewDidFinishRenderingMap(_ mapView: MLNMapView, fullyRendered: Bool) {
            MainActor.assumeIsolated {
                if !self.parent.isMapReady {
                    self.parent.isMapReady = true
                }
            }
        }

        func mapViewDidBecomeIdle(_ mapView: MLNMapView) {
            MainActor.assumeIsolated {
                if !self.parent.isMapReady {
                    self.parent.isMapReady = true
                }
                let center = mapView.centerCoordinate
                self.parent.mapSession.cameraSnapshot = MapCameraSnapshot(
                    lat: center.latitude,
                    lng: center.longitude,
                    zoom: mapView.zoomLevel,
                    bearing: mapView.direction,
                    pitch: mapView.camera.pitch
                )
            }
        }

        func mapView(_ mapView: MLNMapView, didFinishLoading style: MLNStyle) {
            MainActor.assumeIsolated {
                // Flip `isMapReady` the moment the style resolves. The more
                // authoritative `didFinishRenderingMap` / `didBecomeIdle`
                // also flip the flag, but they don't fire until the view
                // has laid out with non-zero bounds — sitting on the
                // loading overlay until then leaves users staring at a
                // spinner while MapLibre silently finishes its first
                // render pass.
                self.parent.styleLoadFailed = false
                self.parent.isMapReady = true

                MapLayers.install(into: style, with: self.parent.zones)
                self.layersInstalled = true
                self.lastZoneIds = self.parent.zones.map(\.id)
                self.lastActiveZoneId = nil  // force applyEndpoints / applyActiveZone on next updateUIView
                // Trigger a re-render pass by nudging SwiftUI state — apply
                // the latest active zone + user position.
                if let active = self.parent.zones.first(where: { $0.id == self.parent.activeZoneId }) {
                    MapLayers.applyEndpoints(for: active, to: style)
                    self.lastActiveZoneId = active.id
                    // Skip the fit when we restored a saved camera; otherwise
                    // the user's preferred zoom would be wiped out the moment
                    // the style finishes loading on tab re-entry.
                    if !self.parent.mapSession.isFollowing, !self.didRestoreCameraSnapshot,
                       self.parent.zoomOverride == nil {
                        self.parent.fit(uiView: mapView, to: active)
                    }
                }
                // One-shot — subsequent zone changes auto-fit normally.
                self.didRestoreCameraSnapshot = false
                MapLayers.applyActiveZone(
                    self.parent.activeZoneId,
                    color: self.parent.activeZoneColor(),
                    to: style
                )
                MapLayers.applyUser(
                    self.parent.displayPosition ?? self.parent.currentPosition,
                    bearing: self.damper.effectiveBearing,
                    to: style
                )
            }
        }

        func mapView(
            _ mapView: MLNMapView,
            regionWillChangeWith reason: MLNCameraChangeReason,
            animated: Bool
        ) {
            MainActor.assumeIsolated {
                defer { self.programmaticCameraChange = false }
                if self.programmaticCameraChange { return }
                let gestures: MLNCameraChangeReason = [
                    .gesturePan, .gesturePinch, .gestureRotate,
                    .gestureZoomIn, .gestureZoomOut,
                    .gestureOneFingerZoom, .gestureTilt
                ]
                if !reason.isDisjoint(with: gestures), self.parent.mapSession.isFollowing {
                    self.parent.mapSession.isFollowing = false
                }
            }
        }
    }
}
#endif
