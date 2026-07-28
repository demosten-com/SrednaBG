// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCarPlay

#if canImport(CarPlay)
import CarPlay
import Observation
import UIKit
import SrednaBGCore
import SrednaBGData
import SrednaBGTracking
import SrednaBGMapCore

/// Owns the CarPlay map template + navigation session + the
/// `withObservationTracking` re-arming loop that drives the UIKit map
/// view and overlay. Mirrors Android's `NavigationScreen` feature
/// contract: map buttons (heading toggle, zoom +/-), mute nav-bar
/// button, and a `CPNavigationSession` bracketing each zone traversal.
@MainActor
final class CarPlaySceneCoordinator {

    private let interfaceController: CPInterfaceController
    private let window: CPWindow
    private let bundle: CarPlayServiceBundle

    private let mapVC = CarPlayMapViewController()
    private lazy var mapTemplate: CPMapTemplate = buildMapTemplate()

    // Map button instances are rebuilt on heading / mute flips so the
    // icon swaps deterministically; keeping stored references lets us
    // find and replace them without rebuilding the whole template.
    private var headingButton: CPMapButton?
    private var zoomInButton: CPMapButton?
    private var zoomOutButton: CPMapButton?
    private var muteButton: CPBarButton?

    private var navigationSession: CPNavigationSession?
    private var lastInZoneId: String?

    init(
        interfaceController: CPInterfaceController,
        window: CPWindow,
        bundle: CarPlayServiceBundle
    ) {
        self.interfaceController = interfaceController
        self.window = window
        self.bundle = bundle
    }

    func start() {
        window.rootViewController = mapVC
        interfaceController.setRootTemplate(mapTemplate, animated: false, completion: nil)

        // Resolve the offline map style URL asynchronously — the first
        // render paints with the bundled placeholder MLNStyle until the
        // rewrite completes. Matches how the phone map tab comes up.
        Task { @MainActor [weak self] in
            guard let self else { return }
            let url = await self.bundle.mapStyleURLProvider()
            if let url {
                self.mapVC.setStyleURL(url)
            }
        }

        // Tracking start is idempotent — if the phone HomeScreen already
        // started it, this is a no-op (guard !isTracking in
        // ZoneTrackingService.start at line 67).
        Task { @MainActor [tracking = bundle.tracking] in
            await tracking.start()
        }

        observe()
    }

    func stop() {
        // Deliberately do NOT call tracking.stop() — the phone
        // HomeScreen's Start/Stop button remains the single authority.
        navigationSession?.finishTrip()
        navigationSession = nil
        window.rootViewController = nil
    }

    // MARK: - Observation loop (self-re-arming)

    private func observe() {
        withObservationTracking {
            _ = bundle.tracking.zoneState
            _ = bundle.tracking.currentPosition
            _ = bundle.tracking.zones
            _ = bundle.tracking.isTracking
            _ = bundle.settings.mapHeadingUp
            _ = bundle.settings.voiceEnabled
            _ = bundle.settings.vehicleType
            apply()
        } onChange: { [weak self] in
            // Observation fires onChange exactly once per registration.
            // Hop to main and re-arm.
            Task { @MainActor [weak self] in self?.observe() }
        }
    }

    private func apply() {
        let tracking = bundle.tracking
        let settings = bundle.settings
        let labels = bundle.labelsProvider()

        let overlay = CarPlaySpeedOverlayModel.from(
            isTracking: tracking.isTracking,
            state: tracking.zoneState,
            currentSpeedKmh: tracking.currentPosition?.speed,
            vehicleType: settings.vehicleType,
            labels: labels
        )

        let activeZoneId: String?
        switch tracking.zoneState {
        case .outside:
            activeZoneId = nil
        case .inZone(let inZone):
            activeZoneId = inZone.zone.id
        // Highlighted like any other in-zone state — we know which zone it is,
        // just not how fast we crossed it.
        case .unmeasured(let unmeasured):
            activeZoneId = unmeasured.zone.id
        case .exiting(let exiting):
            activeZoneId = exiting.zone.id
        }

        let displayPosition = snapToZone(tracking.currentPosition, state: tracking.zoneState)

        mapVC.apply(
            zones: tracking.zones,
            activeZoneId: activeZoneId,
            currentPosition: tracking.currentPosition,
            displayPosition: displayPosition,
            zoneState: tracking.zoneState,
            headingUp: settings.mapHeadingUp,
            overlayModel: overlay
        )

        refreshMuteButton(voiceEnabled: settings.voiceEnabled)
        updateNavigationSession(for: tracking.zoneState)
    }

    // MARK: - Map template

    private func buildMapTemplate() -> CPMapTemplate {
        let template = CPMapTemplate()
        template.automaticallyHidesNavigationBar = false

        let heading = CPMapButton { [weak self] _ in self?.toggleHeading() }
        heading.image = Self.headingIcon(headingUp: bundle.settings.mapHeadingUp)

        let zoomIn = CPMapButton { [weak self] _ in self?.mapVC.zoomIn() }
        zoomIn.image = UIImage(systemName: "plus.magnifyingglass")

        let zoomOut = CPMapButton { [weak self] _ in self?.mapVC.zoomOut() }
        zoomOut.image = UIImage(systemName: "minus.magnifyingglass")

        self.headingButton = heading
        self.zoomInButton = zoomIn
        self.zoomOutButton = zoomOut
        template.mapButtons = [heading, zoomIn, zoomOut]

        let muteImage = Self.muteIcon(voiceEnabled: bundle.settings.voiceEnabled)
            ?? UIImage(systemName: "speaker")
            ?? UIImage()
        let mute = CPBarButton(image: muteImage) { [weak self] _ in
            self?.toggleMute()
        }
        self.muteButton = mute
        template.leadingNavigationBarButtons = [mute]
        template.trailingNavigationBarButtons = []

        return template
    }

    // MARK: - Button actions

    private func toggleHeading() {
        bundle.settings.mapHeadingUp.toggle()
        headingButton?.image = Self.headingIcon(headingUp: bundle.settings.mapHeadingUp)
    }

    private func toggleMute() {
        bundle.settings.voiceEnabled.toggle()
        refreshMuteButton(voiceEnabled: bundle.settings.voiceEnabled)
    }

    private func refreshMuteButton(voiceEnabled: Bool) {
        muteButton?.image = Self.muteIcon(voiceEnabled: voiceEnabled)
    }

    private static func headingIcon(headingUp: Bool) -> UIImage? {
        let name = headingUp ? "location.north.line.fill" : "location.north.fill"
        return UIImage(systemName: name)
    }

    private static func muteIcon(voiceEnabled: Bool) -> UIImage? {
        let name = voiceEnabled ? "speaker.wave.2.fill" : "speaker.slash.fill"
        return UIImage(systemName: name)
    }

    // MARK: - CPNavigationSession lifecycle

    private func updateNavigationSession(for state: ZoneState) {
        switch state {
        // `.unmeasured` runs no navigation session, for the same reason it shows
        // no average: a CarPlay trip card publishes a distance *and an ETA*, and
        // without a measured traversal any ETA we produced would be guidance we
        // have explicitly declined to give. Treated exactly like `.outside`.
        case .outside, .unmeasured:
            if navigationSession != nil {
                navigationSession?.cancelTrip()
                navigationSession = nil
                lastInZoneId = nil
            }
        case .inZone(let inZone):
            if navigationSession == nil {
                navigationSession = startNavigation(for: inZone.zone)
                lastInZoneId = inZone.zone.id
            } else if lastInZoneId != inZone.zone.id {
                // Jumped straight into a different zone (unlikely but
                // possible if the user teleports in a simulator). Reset
                // the session so the travel-estimate card tracks the
                // current zone's endpoints.
                navigationSession?.cancelTrip()
                navigationSession = startNavigation(for: inZone.zone)
                lastInZoneId = inZone.zone.id
            }
            navigationSession?.updateEstimates(
                travelEstimates(for: inZone),
                for: currentManeuver(for: inZone.zone)
            )
        case .exiting:
            navigationSession?.finishTrip()
            navigationSession = nil
            lastInZoneId = nil
        }
    }

    private func startNavigation(for zone: Zone) -> CPNavigationSession? {
        let origin = MKMapItemAdapter.mapItem(
            for: zone.start,
            name: zone.road
        )
        let destination = MKMapItemAdapter.mapItem(
            for: zone.end,
            name: zone.road
        )
        let routeChoice = CPRouteChoice(
            summaryVariants: [zone.direction],
            additionalInformationVariants: [zone.description],
            selectionSummaryVariants: [zone.road]
        )
        let trip = CPTrip(origin: origin, destination: destination, routeChoices: [routeChoice])
        do {
            return mapTemplate.startNavigationSession(for: trip)
        }
    }

    private func travelEstimates(for inZone: ZoneState.InZone) -> CPTravelEstimates {
        let distance = Measurement(value: inZone.distanceRemaining, unit: UnitLength.meters)
        let time = max(0, inZone.speedStatus.timeRemaining)
        return CPTravelEstimates(distanceRemaining: distance, timeRemaining: time)
    }

    private func currentManeuver(for zone: Zone) -> CPManeuver {
        let maneuver = CPManeuver()
        maneuver.instructionVariants = [zone.road]
        return maneuver
    }
}

// MARK: - MKMapItem bridging (CarPlay trip endpoints are MKMapItem-shaped)

import MapKit

private enum MKMapItemAdapter {
    @MainActor
    static func mapItem(for endpoint: ZoneEndpoint, name: String) -> MKMapItem {
        let coord = CLLocationCoordinate2D(latitude: endpoint.lat, longitude: endpoint.lng)
        let placemark = MKPlacemark(coordinate: coord)
        let item = MKMapItem(placemark: placemark)
        item.name = name
        return item
    }
}
#endif
