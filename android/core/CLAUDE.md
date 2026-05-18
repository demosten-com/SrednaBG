# android/core/

Pure Kotlin library (no Android deps) with zone detection, average speed calculation, GPS filtering, geo utilities, map-theme resolution, and zone-status colors. The iOS port at `ios/Packages/SrednaBGCore/` is an independent Swift hand-port of this engine and evolves separately. 8 source files + 10 test files (including real Trakiya zone fixtures).

- `ZoneDetector` (stateful) — receives GPS points, detects zone entry/exit via point-to-polyline distance (<100m) + heading match (±45°)
- `AverageSpeedCalc` — running average + `SpeedStatus` (max speed sustainable for the remainder, `isOverLimit`)
- `GpsFilter` — Kalman-like noise smoothing
- `RoadMatcher` — road/direction matching
- `GeoUtils` — Haversine, bearing, polyline distance
- `MapThemeResolver` — picks the light or dark MapLibre style URI for a given setting + system appearance
- `ZoneStatusColor` — packed-`Int` mapping from `ZoneState` / over-limit flag to the green / amber / red traffic-light value used by both the SwiftUI and UIKit/Compose surfaces

## Build commands

```bash
# Run from android/ (the Gradle root)
./gradlew :core:test   # JUnit 5
```

## Key files

`Models.kt`, `ZoneDetector.kt`, `AverageSpeedCalc.kt`, `GeoUtils.kt`, `RoadMatcher.kt`, `GpsFilter.kt`, `MapThemeResolver.kt`, `ZoneStatusColor.kt`

## Algorithm edge cases

- **Stop detection**: speed < 5 km/h for > 30s → pause timing (rest areas, traffic)
- **GPS dropout**: gap > 10s → don't accumulate distance for the gap
- **Off-ramp detection**: distance from centerline > threshold → exit zone early
- **Zone overlap**: some zones share roads at junctions — handle priority
- **U-turn/re-entry**: treat as new zone traversal
- **Tunnels**: common on Struma motorway — handle gracefully

## Known bug: vehicle-type hardcoded

`ZoneDetector.kt` hardcodes `zone.speedLimits.car` in all three calls to `AverageSpeedCalc.calculate(...)`, so a user who sets `vehicle_type` to truck/bus still sees the car limit.

The Swift port fixes this via `ZoneDetector.update(_:vehicleType:)` in `ios/Packages/SrednaBGCore/Sources/SrednaBGCore/ZoneDetector.swift`.

Backport plan: thread `vehicleType: VehicleType` through `ZoneDetector.update`, plumb it from `LocationTrackingService` reading `SettingsRepository.vehicleType`. Add a parameterized JUnit test mirroring `vehicleTypeChangesEffectiveLimit` in `ZoneDetectorTests.swift`.
