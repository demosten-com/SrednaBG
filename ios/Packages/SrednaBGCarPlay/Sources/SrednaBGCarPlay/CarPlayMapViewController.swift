// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCarPlay

#if os(iOS)
import UIKit
import CoreLocation
@preconcurrency import MapLibre
import SrednaBGCore
import SrednaBGMapCore

/// UIKit host for `MLNMapView` inside the CarPlay window. Port of
/// `MapLibreView.Coordinator` logic with the SwiftUI wrapper peeled off
/// — CarPlay windows expose a raw `UIViewController` rather than a
/// `UIViewRepresentable` surface.
///
/// The MapLibre delegate responsibilities live on `CarPlayMapCoordinator`
/// (non-isolated, `@unchecked Sendable`) to avoid the `unsafeForcedSync`
/// hop that `@MainActor` + `@preconcurrency MLNMapViewDelegate` would
/// otherwise synthesize — same trap SrednaBGUI's `MapLibreView.Coordinator`
/// works around.
@MainActor
final class CarPlayMapViewController: UIViewController {

    // MARK: - Inputs (mutated by the scene coordinator via `apply(...)`)

    fileprivate var currentStyleURL: URL?
    fileprivate var zones: [Zone] = []
    fileprivate var activeZoneId: String?
    fileprivate var currentPosition: GpsPoint?
    fileprivate var displayPosition: GpsPoint?
    fileprivate var zoneState: ZoneState = .outside
    fileprivate var headingUp: Bool = false

    // MARK: - Views

    fileprivate var mapView: MLNMapView!
    let overlayView = CarPlaySpeedOverlayView()
    private let coordinator = CarPlayMapCoordinator()

    override func loadView() {
        let root = UIView()
        root.backgroundColor = .black

        let mv = MLNMapView(frame: .zero)
        mv.delegate = coordinator
        mv.compassView.isHidden = true
        mv.logoView.isHidden = true
        mv.attributionButton.isHidden = true
        mv.automaticallyAdjustsContentInset = false
        mv.showsUserLocation = false
        mv.setCenter(
            CLLocationCoordinate2D(latitude: 42.7339, longitude: 25.4858),
            zoomLevel: 7,
            animated: false
        )
        mv.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(mv)

        overlayView.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(overlayView)

        NSLayoutConstraint.activate([
            mv.topAnchor.constraint(equalTo: root.topAnchor),
            mv.bottomAnchor.constraint(equalTo: root.bottomAnchor),
            mv.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            mv.trailingAnchor.constraint(equalTo: root.trailingAnchor),

            overlayView.topAnchor.constraint(equalTo: root.safeAreaLayoutGuide.topAnchor, constant: 12),
            overlayView.leadingAnchor.constraint(equalTo: root.safeAreaLayoutGuide.leadingAnchor, constant: 16),
            overlayView.trailingAnchor.constraint(equalTo: root.safeAreaLayoutGuide.trailingAnchor, constant: -16)
        ])

        self.mapView = mv
        self.coordinator.owner = self
        self.coordinator.mapView = mv
        self.view = root
    }

    // MARK: - Coordinator-driven updates

    func setStyleURL(_ url: URL?) {
        guard currentStyleURL != url else { return }
        currentStyleURL = url
        coordinator.layersInstalled = false
        if let url {
            mapView?.styleURL = url
        }
    }

    func apply(
        zones: [Zone],
        activeZoneId: String?,
        currentPosition: GpsPoint?,
        displayPosition: GpsPoint?,
        zoneState: ZoneState,
        headingUp: Bool,
        overlayModel: CarPlaySpeedOverlayModel
    ) {
        self.zones = zones
        self.activeZoneId = activeZoneId
        self.currentPosition = currentPosition
        self.displayPosition = displayPosition
        self.zoneState = zoneState
        self.headingUp = headingUp
        overlayView.apply(overlayModel)
        coordinator.applyToMapIfReady()
    }

    // MARK: - Commands from map buttons

    func zoomIn() {
        guard let mv = mapView else { return }
        coordinator.programmaticCameraChange = true
        mv.setZoomLevel(mv.zoomLevel + 1, animated: true)
    }

    func zoomOut() {
        guard let mv = mapView else { return }
        coordinator.programmaticCameraChange = true
        mv.setZoomLevel(max(mv.zoomLevel - 1, mv.minimumZoomLevel), animated: true)
    }

    // MARK: - Helpers exposed to the coordinator

    fileprivate func activeZoneColor() -> UIColor {
        switch zoneState {
        case .inZone(let inZone):
            return statusUIColor(zoneStatusColor(state: inZone, currentSpeedKmh: currentPosition?.speed))
        case .exiting, .outside:
            return MapLayers.activeRedLineColor
        }
    }

    fileprivate func applyFollowCamera(uiView: MLNMapView, position: GpsPoint, damper: BearingDamper) {
        let coord = CLLocationCoordinate2D(latitude: position.lat, longitude: position.lng)
        let altitude = uiView.camera.altitude
        let camera = MLNMapCamera(
            lookingAtCenter: coord,
            altitude: altitude,
            pitch: 0,
            heading: headingUp ? damper.effectiveBearing : 0
        )
        coordinator.programmaticCameraChange = true
        uiView.setCamera(camera, animated: true)
    }

    fileprivate func fit(uiView: MLNMapView, to zone: Zone) {
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
            edgePadding: UIEdgeInsets(top: 96, left: 48, bottom: 120, right: 48),
            animated: true
        )
    }
}

/// MapLibre delegate holder. Non-isolated and `@unchecked Sendable`;
/// each delegate method hops to the main actor via `MainActor.assumeIsolated`.
/// Mirrors `MapLibreView.Coordinator`'s dodge of the `unsafeForcedSync`
/// hop the compiler would synthesize if this class were `@MainActor`.
final class CarPlayMapCoordinator: NSObject, MLNMapViewDelegate, @unchecked Sendable {

    @MainActor weak var owner: CarPlayMapViewController?
    @MainActor weak var mapView: MLNMapView?
    @MainActor var layersInstalled: Bool = false
    @MainActor var lastZoneIds: [String] = []
    @MainActor var lastActiveZoneId: String?
    @MainActor var damper = BearingDamper()
    @MainActor var programmaticCameraChange: Bool = false

    @MainActor
    func applyToMapIfReady() {
        guard let owner, let mapView else { return }
        if let position = owner.currentPosition {
            damper.update(speedKmh: position.speed, bearingDegrees: position.bearing)
        }
        guard let style = mapView.style, layersInstalled else { return }

        let ids = owner.zones.map(\.id)
        if lastZoneIds != ids {
            MapLayers.applyZones(owner.zones, to: style)
            lastZoneIds = ids
        }

        let activeZone = owner.zones.first(where: { $0.id == owner.activeZoneId })
        if lastActiveZoneId != owner.activeZoneId {
            MapLayers.applyEndpoints(for: activeZone, to: style)
            lastActiveZoneId = owner.activeZoneId
            if let zone = activeZone {
                owner.fit(uiView: mapView, to: zone)
            }
        }

        let color = owner.activeZoneColor()
        MapLayers.applyActiveZone(owner.activeZoneId, color: color, to: style)

        MapLayers.applyUser(
            owner.displayPosition ?? owner.currentPosition,
            bearing: damper.effectiveBearing,
            to: style
        )

        if let position = owner.displayPosition ?? owner.currentPosition {
            owner.applyFollowCamera(uiView: mapView, position: position, damper: damper)
        }
    }

    // MARK: - MLNMapViewDelegate

    func mapView(_ mapView: MLNMapView, didFinishLoading style: MLNStyle) {
        MainActor.assumeIsolated {
            guard let owner else { return }
            MapLayers.install(into: style, with: owner.zones)
            self.layersInstalled = true
            self.lastZoneIds = owner.zones.map(\.id)
            self.lastActiveZoneId = nil
            applyToMapIfReady()
        }
    }

    func mapViewDidFailLoadingMap(_ mapView: MLNMapView, withError error: any Error) {
        NSLog("SrednaBG CarPlay MapLibre: style load failed — \(error)")
    }

    // Present in SrednaBGUI's Coordinator with trivial bodies — same
    // render-path quirk applies here: omitting them leaves the vector
    // features unpainted even after the style resolves.
    func mapViewDidFinishRenderingMap(_ mapView: MLNMapView, fullyRendered: Bool) {}
    func mapViewDidBecomeIdle(_ mapView: MLNMapView) {}
}
#endif
