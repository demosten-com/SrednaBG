// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore
//
// Swift port of `android/core/.../HistoryStatsTest.kt`. Keep the cases and the
// shared `history/spike_suppressed.json` fixture in sync across platforms.

import Foundation
import Testing
@testable import SrednaBGCore

struct HistoryStatsTests {

    // MARK: sustainedExtremes

    @Test func emptySeriesYieldsZeroExtremes() {
        let (min, max) = HistoryStats.sustainedExtremes([])
        #expect(min == 0.0)
        #expect(max == 0.0)
    }

    @Test func singleSampleYieldsThatSampleAsBothExtremes() {
        let (min, max) = HistoryStats.sustainedExtremes([SpeedSample(timestampMs: 0, speedKmh: 88.0)])
        #expect(min == 88.0)
        #expect(max == 88.0)
    }

    @Test func constantSeriesYieldsThatConstantForBothExtremes() {
        let samples = (0...10).map { SpeedSample(timestampMs: Int64($0) * 1000, speedKmh: 120.0) }
        let (min, max) = HistoryStats.sustainedExtremes(samples)
        #expect(abs(min - 120.0) < 1e-9)
        #expect(abs(max - 120.0) < 1e-9)
    }

    @Test func singleSampleSpikeCannotBecomeSustainedMax() {
        let samples = [
            SpeedSample(timestampMs: 0, speedKmh: 100.0),
            SpeedSample(timestampMs: 1000, speedKmh: 100.0),
            SpeedSample(timestampMs: 2000, speedKmh: 100.0),
            SpeedSample(timestampMs: 3000, speedKmh: 200.0),
            SpeedSample(timestampMs: 4000, speedKmh: 100.0),
            SpeedSample(timestampMs: 5000, speedKmh: 100.0),
            SpeedSample(timestampMs: 6000, speedKmh: 100.0)
        ]
        let (min, max) = HistoryStats.sustainedExtremes(samples)
        #expect(abs(min - 100.0) < 1e-9)
        #expect(max < 150.0)
    }

    @Test func singleSampleDropCannotBecomeSustainedMin() {
        let samples = [
            SpeedSample(timestampMs: 0, speedKmh: 120.0),
            SpeedSample(timestampMs: 1000, speedKmh: 120.0),
            SpeedSample(timestampMs: 2000, speedKmh: 120.0),
            SpeedSample(timestampMs: 3000, speedKmh: 0.0),
            SpeedSample(timestampMs: 4000, speedKmh: 120.0),
            SpeedSample(timestampMs: 5000, speedKmh: 120.0),
            SpeedSample(timestampMs: 6000, speedKmh: 120.0)
        ]
        let (min, max) = HistoryStats.sustainedExtremes(samples)
        #expect(abs(max - 120.0) < 1e-9)
        #expect(min > 60.0)
    }

    @Test func sustainedClimbIsReflectedInTheMax() {
        let low = (0...9).map { SpeedSample(timestampMs: Int64($0) * 1000, speedKmh: 90.0) }
        let high = (10...19).map { SpeedSample(timestampMs: Int64($0) * 1000, speedKmh: 160.0) }
        let (min, max) = HistoryStats.sustainedExtremes(low + high)
        #expect(abs(min - 90.0) < 1e-6)
        #expect(abs(max - 160.0) < 1e-6)
    }

    @Test func sustainedExtremesMatchesTheSharedSpikeFixture() throws {
        let fx = try loadFixture("history/spike_suppressed")
        let (min, max) = HistoryStats.sustainedExtremes(fx.samples, windowMs: fx.windowMs)
        #expect(abs(min - fx.expectedSustainedMin) < 0.01)
        #expect(abs(max - fx.expectedSustainedMax) < 0.01)
    }

    // MARK: runningAverage

    @Test func runningAverageOfEmptyIsEmpty() {
        #expect(HistoryStats.runningAverage([]).isEmpty)
    }

    @Test func runningAverageOfAConstantSeriesIsThatConstantThroughout() {
        let samples = (0...5).map { SpeedSample(timestampMs: Int64($0) * 1000, speedKmh: 100.0) }
        let avg = HistoryStats.runningAverage(samples)
        #expect(avg.count == samples.count)
        #expect(avg.allSatisfy { abs($0.speedKmh - 100.0) < 1e-9 })
    }

    @Test func runningAverageStartsAtFirstSpeedAndConvergesToTripAverage() {
        let samples = [
            SpeedSample(timestampMs: 0, speedKmh: 60.0),
            SpeedSample(timestampMs: 1000, speedKmh: 120.0),
            SpeedSample(timestampMs: 2000, speedKmh: 120.0),
            SpeedSample(timestampMs: 3000, speedKmh: 120.0),
            SpeedSample(timestampMs: 4000, speedKmh: 120.0),
            SpeedSample(timestampMs: 5000, speedKmh: 120.0)
        ]
        let avg = HistoryStats.runningAverage(samples)
        #expect(abs(avg.first!.speedKmh - 60.0) < 1e-9)
        #expect(zip(avg, avg.dropFirst()).allSatisfy { $1.speedKmh >= $0.speedKmh })
        #expect(avg.last!.speedKmh >= 100.0 && avg.last!.speedKmh <= 120.0)
        #expect(avg.map(\.timestampMs) == samples.map(\.timestampMs))
    }

    @Test func runningAverageIsSmootherThanTheRawSeries() {
        let raw = [70.0, 140.0, 60.0, 150.0, 80.0, 130.0]
        let samples = raw.enumerated().map { SpeedSample(timestampMs: Int64($0.offset) * 1000, speedKmh: $0.element) }
        let avg = HistoryStats.runningAverage(samples).map(\.speedKmh)
        let rawSpread = raw.max()! - raw.min()!
        let avgSpread = avg.max()! - avg.min()!
        #expect(avgSpread < rawSpread)
        #expect(avgSpread > 0.0)
    }

    // MARK: downsample

    @Test func downsamplePassesThroughAShortSeriesUnchanged() {
        let samples = (0...9).map { SpeedSample(timestampMs: Int64($0) * 1000, speedKmh: Double($0)) }
        #expect(HistoryStats.downsample(samples, maxPoints: 500) == samples)
    }

    @Test func downsamplePassesThroughExactlyMaxPointsUnchanged() {
        let samples = (0..<500).map { SpeedSample(timestampMs: Int64($0) * 1000, speedKmh: Double($0)) }
        #expect(HistoryStats.downsample(samples, maxPoints: 500) == samples)
    }

    @Test func downsampleCapsALongSeriesAtMaxPoints() {
        let samples = (0..<5000).map { SpeedSample(timestampMs: Int64($0) * 1000, speedKmh: Double($0)) }
        let out = HistoryStats.downsample(samples, maxPoints: 500)
        #expect(out.count == 500)
        #expect(zip(out, out.dropFirst()).allSatisfy { $0.timestampMs < $1.timestampMs })
        #expect(out.first!.timestampMs >= samples.first!.timestampMs)
        #expect(out.last!.timestampMs <= samples.last!.timestampMs)
    }

    @Test func downsamplePreservesTheAverageSpeedOfARamp() {
        let samples = (0..<2000).map { SpeedSample(timestampMs: Int64($0) * 1000, speedKmh: Double($0)) }
        let out = HistoryStats.downsample(samples, maxPoints: 500)
        let srcAvg = samples.map(\.speedKmh).reduce(0, +) / Double(samples.count)
        let outAvg = out.map(\.speedKmh).reduce(0, +) / Double(out.count)
        #expect(abs(srcAvg - outAvg) < 1.0)
    }

    // MARK: fixture loading

    private struct Fixture: Decodable {
        let windowMs: Int64
        let samples: [SpeedSample]
        let expectedSustainedMin: Double
        let expectedSustainedMax: Double
    }

    private func loadFixture(_ name: String) throws -> Fixture {
        let url = try #require(
            Bundle.module.url(forResource: "Resources/\(name)", withExtension: "json"),
            "fixture not found: \(name)"
        )
        return try JSONDecoder().decode(Fixture.self, from: Data(contentsOf: url))
    }
}
