// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/** Yellow/warning shade tuned for the current system theme.
 *
 * Light theme uses [SpeedAmberDeep] (#E65100) for high contrast against
 * pale amber-tinted cards; dark theme keeps [SpeedAmber] (#F9A825), which
 * already reads cleanly against the dark tinted surfaces HomeScreen uses.
 *
 * Call from any composable that renders the over-speed-warning color
 * (HomeScreen warning cards, InZoneCard yellow band, ZoneMap chip yellow).
 */
@Composable
fun warningAmber(): Color =
    if (isSystemInDarkTheme()) SpeedAmber else SpeedAmberDeep
