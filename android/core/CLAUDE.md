# android/core/

Pure Kotlin library (no Android deps) with zone detection, average speed calculation, GPS filtering, geo utilities, map-theme resolution, and zone-status colors. The iOS port at `ios/Packages/SrednaBGCore/` is an independent Swift hand-port of this engine and evolves separately. 9 source files + 11 test files (including real Trakiya zone fixtures).

- `ZoneDetector` (stateful) — receives GPS points, self-orients each centerline `start → end` at construction, detects zone entry/exit via point-to-polyline distance + heading match (±45°)
- `AverageSpeedCalc` — running average + `SpeedStatus` (max speed sustainable for the remainder, `isOverLimit`)
- `GpsFilter` — Kalman-like noise smoothing
- `RoadMatcher` — road/direction matching
- `GeoUtils` — Haversine, bearing, polyline distance
- `VehicleType` — `CAR`/`TRUCK`/`BUS`/`MOTORCYCLE` enum with per-vehicle `limit(speedLimits)` selection
- `MapThemeResolver` — picks the light or dark MapLibre style URI for a given setting + system appearance
- `ZoneStatusColor` — packed-`Int` mapping from `ZoneState` / over-limit flag to the green / amber / red traffic-light value used by both the SwiftUI and UIKit/Compose surfaces

## Build commands

```bash
# Run from android/ (the Gradle root)
./gradlew :core:test   # JUnit 5
```

## Key files

`Models.kt`, `ZoneDetector.kt`, `AverageSpeedCalc.kt`, `GeoUtils.kt`, `RoadMatcher.kt`, `GpsFilter.kt`, `VehicleType.kt`, `MapThemeResolver.kt`, `ZoneStatusColor.kt`

## Algorithm edge cases

- **Stop detection**: speed < 5 km/h for > 30s → pause timing (rest areas, traffic)
- **GPS dropout**: gap > 10s → don't accumulate distance for the gap
- **Off-ramp detection / off-road exit hysteresis**: an off-road fix (distance from centerline beyond the on-road band) no longer exits on the spot — the smoothed Kalman position lags off the road for a fix or two on a bend (worse on coarsely-sampled server centerlines), and momentary glitches (overpass, tunnel mouth, urban canyon) throw single fixes wide. The in-zone check uses the **zone-appropriate** band (motorway override 150 m, same as entry matching, not the old tight 100 m), and exit requires the off-road condition to persist `OFF_ROAD_EXIT_GRACE_FIXES` (3) consecutive fixes — *unless* the fix is `OFF_ROAD_HARD_M` (1000 m) past the road, a real departure that exits immediately. A genuine off-ramp diverges steadily and trips the streak in a few seconds. Caught by `qa/validate-zones.sh` (struma-02-north / trakiya-01-west / hemus-02-west flapped `InZone → Exiting → InZone` on the coarser **server** centerlines, while the aligned bundle passed); regression `ZoneDetectorTest."transient off-road blip does not exit, but sustained off-road does"` + `"…back on-road within the grace window…"`.
- **Reversed centerline / endpoint orientation**: `ZoneDetector` orients every zone's centerline to run `start → end` once at construction (`orientCenterlineToStart`), so all order-dependent geometry (direction matching, polyline projection, remaining distance, puck snapping) is correct regardless of the stored point order. A centerline stored **end-first** — a real server-data bug; the scraper's `align_centerline_to_endpoints` fixes the bundle, but the live `/api/zones` may still serve it and the device syncs that into Room — would otherwise flip the zone's apparent first→last bearing, so the app matches the **opposite-carriageway sibling** and reports an inverted "remaining" (observed live via `qa/feed-zone.sh 0` on `europa-01-north` → matched `europa-01-south`, the "red dot first"). The `start`/`end` endpoints are authoritative, so the engine recovers without depending on a server redeploy. **Do not** add this as a `by lazy` property on the `Zone` data class — `ZoneRepository` round-trips `Zone` through Gson and the lazy delegate field breaks (de)serialization; orient at the detector boundary instead. Regression `ZoneDetectorTest."reversed-centerline zone still enters the correct sibling (qa feed-zone 0 bug)"` + `"…reports a decreasing, non-inverted remaining"`; on-device `qa/validate-zones.sh --keep-online` (72/72 against the reversed synced data).
- **End-of-zone exit**: `EXIT_DISTANCE_M = 100` (straight-line to `zone.end`) — the average + remainder guidance stay live until the end camera is in sight. The detector orients the centerline to actually reach `zone.end` (see above); a polyline-remaining ≤ 0 backstop also covers the case where `zone.end` is offset from the road.
- **Distance source split**: the speed×time integrator (`distanceTraveled`) feeds *only* the average-speed numerator; everything position-related (remaining label, progress, max-for-remainder, exit, mid-zone entry) is derived from `projectOntoPolyline` against the centerline arc length (`polylineLengthMeters`), which is drift-free. This is why uneven simulated traces / noisy GPS speed can't fake a mid-zone exit or collapse the remainder to 0. Regression: `ZoneDetectorTest."dense short-segment zone is a single clean traversal"` + `qa/scenarios/edge/dense_centerline.py`.
- **Zone overlap**: some zones share roads at junctions — handle priority
- **U-turn/re-entry**: treat as new zone traversal — but a point *past* the end on the same straight road must NOT re-enter the just-finished zone; the mid-zone cold-start gate requires polyline-remaining > `EXIT_DISTANCE_M`, which is ~0 once past the end
- **Hooked centerline tail / end-of-zone re-entry**: the mid-zone cold-start gate is `remaining > EXIT_DISTANCE_M` **and** `distanceToZoneEnd > EXIT_DISTANCE_M`. The polyline-remaining clause alone is insufficient when a centerline hooks/overshoots at its tail: two of its legs then run within metres of each other near the end, so `projectOntoPolyline` can snap a just-exited point onto the *earlier* leg and report a large `remaining`, briefly re-admitting the zone we are exiting (`Exiting → InZone → Exiting` flap on the final ~100 m). The straight-line `distanceToZoneEnd` clause closes that — we are finishing the zone there, not joining it late. Caught by `qa/validate-zones.sh` (11/72 zones flapped at the tail before the guard); see `qa/CLAUDE.md`.
- **Tunnels**: common on Struma motorway — handle gracefully

## Vehicle-type-aware speed limit

`ZoneDetector.update(point, vehicleType)` takes a `VehicleType` (`CAR`/`TRUCK`/`BUS`/`MOTORCYCLE`, default `CAR`) and passes `vehicleType.limit(zone.speedLimits)` into every `AverageSpeedCalc.calculate(...)`, so a user who sets `vehicle_type` to truck/bus/motorcycle gets that limit (motorcycle falls back to the car limit when a zone has none). `LocationTrackingService` mirrors `SettingsRepository.vehicleType` into `currentVehicleType` via a `lifecycleScope` collector and threads it into the detector call. Regression: `ZoneDetectorTest."vehicle type changes effective limit"`. This was ported from the Swift core; the iOS `ZoneDetector.update(_:vehicleType:)` is the equivalent.

## iOS engine parity

The Swift hand-port at `ios/Packages/SrednaBGCore/` tracks this engine's behavior: centerline orientation to `start → end` (`orientCenterlineToStart`), off-road exit hysteresis (`offRoadExitGraceFixes = 3` / `offRoadHardM = 1000`), `exitDistanceM = 100`, polyline-arc-length remaining (`polylineLengthMeters`), the `distanceRemainingOverride` split, and vehicle-type-aware limits. The co-located-camera TTS case (`Exiting → InZone` announces entering the next zone) lives in `ios/.../AnnouncementPolicy.swift`, mirroring `AudioAlertManager.onZoneStateChanged`.
