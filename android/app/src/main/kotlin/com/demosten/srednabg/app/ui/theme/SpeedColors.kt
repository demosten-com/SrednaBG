// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/** Yellow/warning shade tuned for the current system theme, mirroring iOS's
 * dynamic `Theme.statusAmber`.
 *
 * Light theme uses [SpeedAmberDeep] (#B8860B) for high contrast against
 * pale amber-tinted cards; dark theme uses the brighter [SpeedAmberLight]
 * (#FDD835), matching the iOS HomeScreen amber in dark mode.
 *
 * Call from any composable that renders the over-speed-warning color
 * (HomeScreen warning cards, InZoneCard yellow band).
 */
@Composable
fun warningAmber(): Color =
    if (isSystemInDarkTheme()) SpeedAmberLight else SpeedAmberDeep

/** Green "within limit" status shade — [SpeedGreenLight] (#66BB6A) in both
 * light and dark, matching the iOS HomeScreen (`Theme.statusGreen`), which is
 * theme-independent. */
fun speedGreen(): Color = SpeedGreenLight

/** Red "over limit" status shade — [SpeedRedLight] (#EF5350) in both light and
 * dark, matching the iOS HomeScreen (`Theme.statusRed`), which is
 * theme-independent. */
fun speedRed(): Color = SpeedRedLight
