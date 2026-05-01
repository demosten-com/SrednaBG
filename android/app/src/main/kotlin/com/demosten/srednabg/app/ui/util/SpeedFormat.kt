// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.util

const val DASH_PLACEHOLDER = "--"

fun Double?.orDash(format: String = "%d"): String {
    if (this == null || isNaN() || isInfinite()) return DASH_PLACEHOLDER
    return format.format(if (format.contains("d")) toInt() else this)
}
