// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Foundation
import Testing
@testable import SrednaBGCore

@Suite("MapThemeResolver")
struct MapThemeResolverTests {

    private func utc(year: Int, month: Int, day: Int, hour: Int, minute: Int = 0) -> Date {
        var components = DateComponents()
        components.year = year
        components.month = month
        components.day = day
        components.hour = hour
        components.minute = minute
        components.second = 0
        components.timeZone = TimeZone(identifier: "UTC")
        return Calendar(identifier: .gregorian).date(from: components)!
    }

    private func sofiaPoint() -> GpsPoint {
        GpsPoint(lat: 42.7, lng: 23.3, speed: 0, timestamp: 0, bearing: 0)
    }

    @Test
    func manualLightModeIgnoresTimeAndPosition() {
        let midnight = utc(year: 2026, month: 12, day: 21, hour: 0)
        #expect(MapThemeResolver.resolve(mode: .light, position: sofiaPoint(), now: midnight) == .light)
    }

    @Test
    func manualDarkModeIgnoresTimeAndPosition() {
        let noon = utc(year: 2026, month: 6, day: 21, hour: 12)
        #expect(MapThemeResolver.resolve(mode: .dark, position: sofiaPoint(), now: noon) == .dark)
    }

    @Test
    func autoNoonSummerSofiaIsLight() {
        let t = utc(year: 2026, month: 6, day: 21, hour: 12)
        #expect(MapThemeResolver.resolve(mode: .auto, position: sofiaPoint(), now: t) == .light)
    }

    @Test
    func autoLocalMidnightWinterSofiaIsDark() {
        let t = utc(year: 2026, month: 12, day: 21, hour: 22)
        #expect(MapThemeResolver.resolve(mode: .auto, position: sofiaPoint(), now: t) == .dark)
    }

    @Test
    func autoWithNoGpsFallsBackToSofia() {
        let t = utc(year: 2026, month: 6, day: 21, hour: 12)
        #expect(MapThemeResolver.resolve(mode: .auto, position: nil, now: t) == .light)
    }

    @Test
    func autoDeepNightAnyBulgariaPositionIsDark() {
        let t = utc(year: 2026, month: 12, day: 21, hour: 0)
        let varna = GpsPoint(lat: 43.21, lng: 27.91, speed: 0, timestamp: 0, bearing: 0)
        #expect(MapThemeResolver.resolve(mode: .auto, position: varna, now: t) == .dark)
    }

    @Test
    func solarAltitudeIsHighAtSummerNoonSofia() {
        let t = utc(year: 2026, month: 6, day: 21, hour: 10)
        let alt = MapThemeResolver.solarAltitudeDegrees(lat: 42.7, lng: 23.3, now: t)
        #expect(alt > 65.0, "expected high altitude, got \(alt)")
    }

    @Test
    func solarAltitudeIsWellBelowHorizonAtWinterMidnightSofia() {
        let t = utc(year: 2026, month: 12, day: 21, hour: 22)
        let alt = MapThemeResolver.solarAltitudeDegrees(lat: 42.7, lng: 23.3, now: t)
        #expect(alt < -50.0, "expected very negative altitude, got \(alt)")
    }

    @Test
    func boundaryNearCivilTwilightSofiaEvening() {
        // 2026-09-23 in Sofia: sunset ~18:48 local (15:48 UTC), civil
        // twilight ends ~19:18 local (16:18 UTC).
        let brightAfternoon = utc(year: 2026, month: 9, day: 23, hour: 14)
        let deepEvening = utc(year: 2026, month: 9, day: 23, hour: 19)
        #expect(MapThemeResolver.resolve(mode: .auto, position: sofiaPoint(), now: brightAfternoon) == .light)
        #expect(MapThemeResolver.resolve(mode: .auto, position: sofiaPoint(), now: deepEvening) == .dark)
    }
}
