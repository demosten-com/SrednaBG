// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGUI

import Charts
import SwiftUI
import SrednaBGCore

/// Within/over verdict tint, mirroring Android's `historyVerdictColor`: green
/// when the driver's final average stayed within the limit, red when over.
func historyVerdictColor(isOverLimit: Bool) -> Color {
    isOverLimit ? Theme.statusRed : Theme.statusGreen
}

/// Format an elapsed-seconds value as `m:ss` for the graph's time axis, matching
/// the "Duration" field in the detail header (so `100` reads as `1:40`, not an
/// unlabeled number).
func elapsedTimeLabel(_ seconds: Double) -> String {
    let total = max(0, Int(seconds.rounded()))
    return String(format: "%d:%02d", total / 60, total % 60)
}

// The three graph series colours, shared between the chart and its legend so the
// two can never disagree. These are handed to Swift Charts through an explicit
// `.chartForegroundStyleScale`, NOT via per-mark `.foregroundStyle(.secondary/
// .accentColor)`: those are *semantic* styles that Charts resolves against the
// plot's base foreground, so once two of them coexist Charts auto-builds a style
// scale and repaints the lines (the average came out faded-green, then the speed
// came out white). Naming each series and pinning the scale is the deterministic
// path — the limit already rendered correctly because `Theme.statusRed` is a
// concrete colour.
let historySpeedColor = Theme.statusGreen
let historyAverageColor = Color.primary
let historyLimitColor = Theme.statusRed

/// Series names — used both as the `.foregroundStyle(by:)` key and the scale key.
private enum HistorySeries {
    static let speed = "speed"
    static let average = "average"
}

/// Speed-over-time graph for a completed traversal (Swift Charts, a system
/// framework — no new dependency). X = time since entry (m:ss), Y = km/h. Three
/// layers, mirroring Android's `SpeedGraph`:
///   1. Running-average band — `HistoryStats.runningAverage` as a filled area
///      (0.22 alpha, exact parity with Android's `SpeedGraph`) plus its top-edge
///      line. The app's core metric; it evolves
///      toward the final average and is *not* a flat reference line.
///   2. Zone limit — the one horizontal dashed reference line, in the limit/red.
///   3. Instantaneous speed curve on top.
struct SpeedGraph: View {
    let samples: [SpeedSample]
    let limitKmh: Int
    let avgSpeedKmh: Double?

    private struct Point: Identifiable {
        // Identity keyed on the sample timestamp (stable across renders) rather
        // than a fresh UUID() — an unstable id makes Swift Charts re-animate /
        // flicker the curves on every unrelated parent-state change.
        let timestampMs: Int64
        let t: Double      // seconds since entry
        let speed: Double
        var id: Int64 { timestampMs }
    }

    var body: some View {
        // Guard: nothing meaningful to draw for < 2 samples.
        if samples.count < 2 {
            Color.clear.frame(height: 200)
        } else {
            chart
                .frame(height: 200)
        }
    }

    private var chart: some View {
        let sorted = samples.sorted { $0.timestampMs < $1.timestampMs }
        let t0 = sorted[0].timestampMs
        let speedPoints = sorted.map {
            Point(timestampMs: $0.timestampMs, t: Double($0.timestampMs - t0) / 1000, speed: $0.speedKmh)
        }
        let avgPoints = HistoryStats.runningAverage(sorted).map {
            Point(timestampMs: $0.timestampMs, t: Double($0.timestampMs - t0) / 1000, speed: $0.speedKmh)
        }

        // Y ceiling: headroom above the fastest sample / limit / average, with a
        // floor so a slow zone still renders readably (matches Android).
        let maxSample = sorted.map(\.speedKmh).max() ?? 0
        let ceiling = max(maxSample, Double(limitKmh), avgSpeedKmh ?? 0)
        let maxY = max(ceiling * 1.15, 20)

        // Pin the X domain to the actual traversal length so the curve spans the
        // full width. Without this, Swift Charts auto-pads the domain out to a
        // rounded tick past the last sample, leaving dead space on the right that
        // reads as a graph that "stops short" — and worse for shorter drives.
        let maxT = max(speedPoints.last?.t ?? 1, 1)

        return Chart {
            // 1. Running-average band + its top edge. The band fill is an
            //    explicit low-alpha colour (not part of the scale / legend); the
            //    edge line is coloured via the series scale below.
            ForEach(avgPoints) { p in
                AreaMark(x: .value("t", p.t), y: .value("avg", p.speed))
                    .foregroundStyle(historyAverageColor.opacity(0.22))
                    .interpolationMethod(.monotone)
            }
            ForEach(avgPoints) { p in
                LineMark(
                    x: .value("t", p.t),
                    y: .value("avg", p.speed),
                    series: .value("series", HistorySeries.average)
                )
                .foregroundStyle(by: .value("series", HistorySeries.average))
                .lineStyle(StrokeStyle(lineWidth: 2))
                .interpolationMethod(.monotone)
            }

            // 2. Zone limit reference — the one horizontal dashed line. Concrete
            //    colour, kept out of the series scale.
            if limitKmh > 0 {
                RuleMark(y: .value("limit", limitKmh))
                    .foregroundStyle(historyLimitColor)
                    .lineStyle(StrokeStyle(lineWidth: 2, dash: [6, 4]))
            }

            // 3. Instantaneous speed curve on top.
            ForEach(speedPoints) { p in
                LineMark(
                    x: .value("t", p.t),
                    y: .value("speed", p.speed),
                    series: .value("series", HistorySeries.speed)
                )
                .foregroundStyle(by: .value("series", HistorySeries.speed))
                .lineStyle(StrokeStyle(lineWidth: 2.5))
                .interpolationMethod(.monotone)
            }
        }
        .chartForegroundStyleScale([
            HistorySeries.speed: historySpeedColor,
            HistorySeries.average: historyAverageColor
        ])
        .chartLegend(.hidden)
        .chartYScale(domain: 0...maxY)
        .chartXScale(domain: 0...maxT)
        .chartYAxis {
            AxisMarks(position: .leading)
        }
        .chartXAxis {
            AxisMarks { value in
                AxisGridLine()
                AxisTick()
                AxisValueLabel {
                    if let seconds = value.as(Double.self) {
                        Text(elapsedTimeLabel(seconds))
                    }
                }
            }
        }
    }
}

/// The Speed / Average / Limit legend under the graph.
struct SpeedGraphLegend: View {
    var body: some View {
        HStack(spacing: 16) {
            legendDot(historySpeedColor, L10n.historyLegendSpeed)
            legendDot(historyAverageColor, L10n.historyLegendAverage)
            legendDot(historyLimitColor, L10n.historyLegendLimit)
        }
        .font(.caption2)
        .foregroundStyle(.secondary)
    }

    private func legendDot(_ color: Color, _ label: String) -> some View {
        HStack(spacing: 4) {
            Circle().fill(color).frame(width: 10, height: 10)
            Text(label)
        }
    }
}
