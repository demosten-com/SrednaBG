// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGUI

import SwiftUI
import SrednaBGCore

/// 128 pt numeric speed readout, color-driven by `StatusColor`. Mirrors the
/// hero number in `HomeScreen.kt`'s in-zone card.
public struct SpeedDisplay: View {
    public let value: Double?
    public let label: String
    public let statusColor: Color

    public init(value: Double?, label: String, statusColor: Color = .primary) {
        self.value = value
        self.label = label
        self.statusColor = statusColor
    }

    public var body: some View {
        VStack(spacing: 4) {
            Text(formatted(value))
                .font(.system(size: 128, weight: .bold, design: .rounded))
                .foregroundStyle(statusColor)
                .monospacedDigit()
                .accessibilityLabel(formatted(value))
            Text(label)
                .font(.title3)
                .foregroundStyle(.secondary)
        }
    }

    /// "--" placeholder for nil values — matches the cross-platform UI rule
    /// that nullable numerics keep their slot visible (see auto-memory feedback).
    private func formatted(_ value: Double?) -> String {
        guard let value, value.isFinite else { return "--" }
        return String(Int(value.rounded()))
    }
}
