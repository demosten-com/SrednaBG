// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.util

import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Locale

/** GitHub-style short form of the zone-data hash: `sha256:` prefix dropped, first 16 hex chars. */
fun shortZoneHash(raw: String?): String {
    val hex = raw?.removePrefix("sha256:").orEmpty()
    return if (hex.isBlank()) DASH_PLACEHOLDER else hex.take(16)
}

/** Renders the zones.json ISO-8601 `version` timestamp in the locale's short date+time form. */
fun formatZoneVersion(
    iso: String?,
    locale: Locale = Locale.getDefault(),
    zoneId: ZoneId = ZoneId.systemDefault(),
): String {
    if (iso.isNullOrBlank()) return DASH_PLACEHOLDER
    return runCatching {
        DateTimeFormatter.ofLocalizedDateTime(FormatStyle.SHORT)
            .withLocale(locale)
            .withZone(zoneId)
            .format(Instant.parse(iso))
    }.getOrDefault(DASH_PLACEHOLDER)
}
