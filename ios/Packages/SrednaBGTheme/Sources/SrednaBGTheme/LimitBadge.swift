// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTheme

import SwiftUI

/// Round white badge with red border — the iconic Bulgarian speed-limit
/// glyph used on road signs. Same component drives the in-app HUD chip
/// (`StatusChip`) and the Lock-Screen / Dynamic Island Live Activity, so
/// the visual stays identical across surfaces.
///
/// Glyph size and stroke scale proportionally with `size` so the badge looks
/// right at HUD scale (48 pt), Dynamic Island expanded (44 pt), and Lock
/// Screen lockup (42 pt).
public struct LimitBadge: View {
    public let limit: Int
    public let size: CGFloat

    public init(limit: Int, size: CGFloat = 48) {
        self.limit = limit
        self.size = size
    }

    public var body: some View {
        Text(String(limit))
            .font(.system(size: size * 0.42, weight: .bold))
            .monospacedDigit()
            .foregroundStyle(Color.black)
            .lineLimit(1)
            .minimumScaleFactor(0.6)
            .frame(width: size, height: size)
            .background(Color.white, in: Circle())
            .overlay(Circle().stroke(Theme.statusRed, lineWidth: max(2, size * 0.075)))
    }
}
