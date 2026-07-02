// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.util

import androidx.appcompat.app.AppCompatDelegate
import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import com.demosten.srednabg.R
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Locale

/**
 * The locale the app is actually displaying in — the per-app override applied via
 * [AppCompatDelegate.setApplicationLocales] (see `SrednaBGApp.applyPersistedLocale`),
 * falling back to the system default when the user hasn't chosen one. History dates
 * must format in this locale, not the raw system locale, mirroring the iOS port which
 * threads the resolved app language into its formatters.
 */
private fun appLocale(): Locale =
    AppCompatDelegate.getApplicationLocales()[0] ?: Locale.getDefault()

/** Local calendar day of an epoch-ms instant — the History list's grouping key. */
fun epochDay(epochMs: Long, zoneId: ZoneId = ZoneId.systemDefault()): Long =
    Instant.ofEpochMilli(epochMs).atZone(zoneId).toLocalDate().toEpochDay()

/** Localized medium date for a History day-group header (e.g. "1 Jul 2026"). */
fun formatHistoryDay(
    epochMs: Long,
    locale: Locale = appLocale(),
    zoneId: ZoneId = ZoneId.systemDefault(),
): String {
    val date = Instant.ofEpochMilli(epochMs).atZone(zoneId).toLocalDate()
    return date.format(
        DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM).withLocale(locale),
    )
}

/** Localized short time for a list row (e.g. "14:32"). */
fun formatHistoryTime(
    epochMs: Long,
    locale: Locale = appLocale(),
    zoneId: ZoneId = ZoneId.systemDefault(),
): String = DateTimeFormatter.ofLocalizedTime(FormatStyle.SHORT)
    .withLocale(locale)
    .withZone(zoneId)
    .format(Instant.ofEpochMilli(epochMs))

/** Localized short date + time for the detail entry/exit labels. */
fun formatHistoryDateTime(
    epochMs: Long,
    locale: Locale = appLocale(),
    zoneId: ZoneId = ZoneId.systemDefault(),
): String = DateTimeFormatter.ofLocalizedDateTime(FormatStyle.SHORT)
    .withLocale(locale)
    .withZone(zoneId)
    .format(Instant.ofEpochMilli(epochMs))

/**
 * Clock-style duration for a traversal: `M:SS`, or `H:MM:SS` past an hour.
 * Locale-neutral (digits + colons), so no per-language string is needed.
 */
/**
 * Canonical compass key for a stored zone direction, or null if it isn't one of
 * the known values (render nothing rather than raw/unknown text). Pure so the
 * mapping is unit-testable without Android resources.
 */
fun directionKey(direction: String): String? =
    when (direction.trim().lowercase(Locale.US)) {
        "east" -> "east"
        "west" -> "west"
        "north" -> "north"
        "south" -> "south"
        else -> null
    }

/** Localized compass label for a stored zone direction (null when unknown). */
@Composable
fun directionLabel(direction: String): String? = when (directionKey(direction)) {
    "east" -> stringResource(R.string.history_direction_east)
    "west" -> stringResource(R.string.history_direction_west)
    "north" -> stringResource(R.string.history_direction_north)
    "south" -> stringResource(R.string.history_direction_south)
    else -> null
}

fun formatDuration(durationMs: Long): String {
    val totalSec = (durationMs / 1000).coerceAtLeast(0)
    val h = totalSec / 3600
    val m = (totalSec % 3600) / 60
    val s = totalSec % 60
    return if (h > 0) {
        String.format(Locale.US, "%d:%02d:%02d", h, m, s)
    } else {
        String.format(Locale.US, "%d:%02d", m, s)
    }
}
