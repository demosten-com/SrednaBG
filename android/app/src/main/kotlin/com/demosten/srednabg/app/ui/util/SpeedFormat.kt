// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.util

const val DASH_PLACEHOLDER = "--"

// An integer conversion specifier (`%d`/`%o`/`%x`/`%X`, with optional flags/width)
// requires an Int arg; a float specifier (`%.1f`) takes the Double as-is. Match the
// specifier explicitly instead of sniffing for a bare 'd', which would mis-fire on
// a literal 'd' elsewhere in the format string (e.g. "%.1f km/h — done").
private val INT_CONVERSION = Regex("%[-#+ 0,(]*\\d*[doxX]")

fun Double?.orDash(format: String = "%d"): String {
    if (this == null || isNaN() || isInfinite()) return DASH_PLACEHOLDER
    return format.format(if (INT_CONVERSION.containsMatchIn(format)) toInt() else this)
}
