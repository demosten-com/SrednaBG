// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGMapCore

#if os(iOS)
import Foundation
import CoreLocation
import UIKit
import MapLibre
import SrednaBGCore

/// Builds GeoJSON feature collections + installs the MapLibre style layers
/// for zones, zone endpoints, and the user-location arrow. Kept separate
/// from `MapLibreView` so the `Coordinator` stays focused on state
/// transitions.
public enum MapLayers {

    // MARK: - Identifiers

    public static let zonesSourceId = "zones"
    public static let endpointsSourceId = "zone-endpoints"
    public static let userSourceId = "user-position"

    public static let zonesInactiveLayerId = "zones-inactive"
    public static let zonesActiveLayerId = "zones-active"
    public static let endpointsStartLayerId = "endpoints-start"
    public static let endpointsEndLayerId = "endpoints-end"
    public static let userLayerId = "user-position"

    /// Sentinel placed into the filter when no zone is active. Avoids the
    /// need to remove/re-add the `zones-active` layer on every state flip.
    public static let inactiveSentinel = "__srednabg_none__"

    // MARK: - Colors

    public static let inactiveLineColor = UIColor(red: 0x15 / 255, green: 0x65 / 255, blue: 0xC0 / 255, alpha: 1)
    public static let activeRedLineColor = UIColor(red: 0xD3 / 255, green: 0x2F / 255, blue: 0x2F / 255, alpha: 1)
    public static let startEndpointColor = UIColor(red: 0x66 / 255, green: 0xBB / 255, blue: 0x6A / 255, alpha: 1)
    public static let endEndpointColor = UIColor(red: 0xEF / 255, green: 0x53 / 255, blue: 0x50 / 255, alpha: 1)

    // MARK: - Feature builders

    public static func zoneFeatures(from zones: [Zone]) -> [MLNPolylineFeature] {
        zones.compactMap { zone in
            guard zone.centerline.count >= 2 else { return nil }
            var coords = zone.centerline.map { pair in
                CLLocationCoordinate2D(latitude: pair[0], longitude: pair[1])
            }
            let feature = MLNPolylineFeature(coordinates: &coords, count: UInt(coords.count))
            feature.identifier = zone.id
            feature.attributes = [
                "id": zone.id,
                "road": zone.road,
                "direction": zone.direction
            ]
            return feature
        }
    }

    public static func endpointFeatures(for zone: Zone?) -> [MLNPointFeature] {
        guard let zone else { return [] }
        let start = MLNPointFeature()
        start.coordinate = CLLocationCoordinate2D(latitude: zone.start.lat, longitude: zone.start.lng)
        start.attributes = ["endpoint": "start"]

        let end = MLNPointFeature()
        end.coordinate = CLLocationCoordinate2D(latitude: zone.end.lat, longitude: zone.end.lng)
        end.attributes = ["endpoint": "end"]

        return [start, end]
    }

    public static func userFeature(for position: GpsPoint?) -> [MLNPointFeature] {
        guard let position else { return [] }
        let point = MLNPointFeature()
        point.coordinate = CLLocationCoordinate2D(latitude: position.lat, longitude: position.lng)
        return [point]
    }

    // MARK: - Layer installation

    /// Adds all sources + layers to the style. Safe to call once per
    /// `didFinishLoading`; subsequent refreshes use `applyZones`,
    /// `applyEndpoints`, and `applyUser`.
    public static func install(into style: MLNStyle, with zones: [Zone]) {
        let zonesSource = MLNShapeSource(
            identifier: zonesSourceId,
            features: zoneFeatures(from: zones),
            options: nil
        )
        style.addSource(zonesSource)

        let endpointsSource = MLNShapeSource(
            identifier: endpointsSourceId,
            features: [],
            options: nil
        )
        style.addSource(endpointsSource)

        let userSource = MLNShapeSource(
            identifier: userSourceId,
            features: [],
            options: nil
        )
        style.addSource(userSource)

        let inactive = MLNLineStyleLayer(identifier: zonesInactiveLayerId, source: zonesSource)
        inactive.predicate = NSPredicate(format: "id != %@", inactiveSentinel)
        inactive.lineColor = NSExpression(forConstantValue: inactiveLineColor)
        inactive.lineWidth = NSExpression(forConstantValue: 4)
        inactive.lineOpacity = NSExpression(forConstantValue: 0.8)
        inactive.lineCap = NSExpression(forConstantValue: "round")
        inactive.lineJoin = NSExpression(forConstantValue: "round")
        style.addLayer(inactive)

        let active = MLNLineStyleLayer(identifier: zonesActiveLayerId, source: zonesSource)
        active.predicate = NSPredicate(format: "id == %@", inactiveSentinel)  // starts filtered out
        active.lineColor = NSExpression(forConstantValue: activeRedLineColor)
        active.lineWidth = NSExpression(forConstantValue: 6)
        active.lineOpacity = NSExpression(forConstantValue: 1)
        active.lineCap = NSExpression(forConstantValue: "round")
        active.lineJoin = NSExpression(forConstantValue: "round")
        style.addLayer(active)

        let endpointsStart = MLNCircleStyleLayer(identifier: endpointsStartLayerId, source: endpointsSource)
        endpointsStart.predicate = NSPredicate(format: "endpoint == %@", "start")
        endpointsStart.circleColor = NSExpression(forConstantValue: startEndpointColor)
        endpointsStart.circleRadius = NSExpression(forConstantValue: 8)
        endpointsStart.circleStrokeColor = NSExpression(forConstantValue: UIColor.white)
        endpointsStart.circleStrokeWidth = NSExpression(forConstantValue: 2)
        style.addLayer(endpointsStart)

        let endpointsEnd = MLNCircleStyleLayer(identifier: endpointsEndLayerId, source: endpointsSource)
        endpointsEnd.predicate = NSPredicate(format: "endpoint == %@", "end")
        endpointsEnd.circleColor = NSExpression(forConstantValue: endEndpointColor)
        endpointsEnd.circleRadius = NSExpression(forConstantValue: 8)
        endpointsEnd.circleStrokeColor = NSExpression(forConstantValue: UIColor.white)
        endpointsEnd.circleStrokeWidth = NSExpression(forConstantValue: 2)
        style.addLayer(endpointsEnd)

        style.setImage(MapUserArrow.makeImage(), forName: MapUserArrow.imageName)

        let user = MLNSymbolStyleLayer(identifier: userLayerId, source: userSource)
        user.iconImageName = NSExpression(forConstantValue: MapUserArrow.imageName)
        user.iconRotationAlignment = NSExpression(forConstantValue: "map")
        user.iconAllowsOverlap = NSExpression(forConstantValue: true)
        user.iconIgnoresPlacement = NSExpression(forConstantValue: true)
        style.addLayer(user)
    }

    // MARK: - Reactive updates

    public static func applyZones(_ zones: [Zone], to style: MLNStyle) {
        guard let source = style.source(withIdentifier: zonesSourceId) as? MLNShapeSource else { return }
        source.shape = MLNShapeCollectionFeature(shapes: zoneFeatures(from: zones))
    }

    public static func applyActiveZone(_ zoneId: String?, color: UIColor, to style: MLNStyle) {
        guard let active = style.layer(withIdentifier: zonesActiveLayerId) as? MLNLineStyleLayer,
              let inactive = style.layer(withIdentifier: zonesInactiveLayerId) as? MLNLineStyleLayer
        else { return }
        let id = zoneId ?? inactiveSentinel
        active.predicate = NSPredicate(format: "id == %@", id)
        inactive.predicate = NSPredicate(format: "id != %@", id)
        active.lineColor = NSExpression(forConstantValue: color)
    }

    public static func applyEndpoints(for zone: Zone?, to style: MLNStyle) {
        guard let source = style.source(withIdentifier: endpointsSourceId) as? MLNShapeSource else { return }
        source.shape = MLNShapeCollectionFeature(shapes: endpointFeatures(for: zone))
    }

    public static func applyUser(
        _ position: GpsPoint?,
        bearing: Double,
        to style: MLNStyle
    ) {
        guard let source = style.source(withIdentifier: userSourceId) as? MLNShapeSource else { return }
        source.shape = MLNShapeCollectionFeature(shapes: userFeature(for: position))

        guard let layer = style.layer(withIdentifier: userLayerId) as? MLNSymbolStyleLayer else { return }
        // Map-aligned rotation — the icon turns with the map, so applying the
        // raw heading is correct in both north-up and heading-up cameras.
        let rotation = BearingDamper.normalize(bearing)
        layer.iconRotation = NSExpression(forConstantValue: rotation)
    }
}
#endif
