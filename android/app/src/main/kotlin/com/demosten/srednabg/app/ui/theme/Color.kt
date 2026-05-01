// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.theme

import androidx.compose.ui.graphics.Color

// Speed status colors
val SpeedGreen = Color(0xFF2E7D32)
val SpeedAmber = Color(0xFFF9A825)
val SpeedRed = Color(0xFFC62828)

val SpeedGreenLight = Color(0xFF66BB6A)
val SpeedAmberLight = Color(0xFFFDD835)
val SpeedRedLight = Color(0xFFEF5350)

// Brand accent — same #4CAF50 used by the marketing site and iOS AccentColor.
// Used for primary + secondary in both light and dark schemes so the active tab
// pill, filled buttons, and other tinted surfaces stay on-brand regardless of
// system theme.
private val BrandGreen = Color(0xFF4CAF50)
private val BrandGreenDeep = Color(0xFF1B5E20) // Material Green 900
private val BrandGreenSoft = Color(0xFFC8E6C9) // Material Green 100

// Light theme
val PrimaryLight = BrandGreen
val OnPrimaryLight = Color(0xFFFFFFFF)
val PrimaryContainerLight = BrandGreenSoft
val OnPrimaryContainerLight = BrandGreenDeep
val SecondaryLight = BrandGreen
val OnSecondaryLight = Color(0xFFFFFFFF)
val SecondaryContainerLight = BrandGreenSoft
val OnSecondaryContainerLight = BrandGreenDeep
val BackgroundLight = Color(0xFFFDFBFF)
val OnBackgroundLight = Color(0xFF1A1C1E)
val SurfaceLight = Color(0xFFFDFBFF)
val OnSurfaceLight = Color(0xFF1A1C1E)
// Surface family — explicit neutral greys so the M3 baseline (purple-seeded)
// containers don't leak through. surfaceTint locks elevation overlays to the
// brand green.
val SurfaceVariantLight = Color(0xFFDFE4DD)
val OnSurfaceVariantLight = Color(0xFF43483F)
val SurfaceContainerLowestLight = Color(0xFFFFFFFF)
val SurfaceContainerLowLight = Color(0xFFF6F8F2)
val SurfaceContainerLight = Color(0xFFF0F2EC)
val SurfaceContainerHighLight = Color(0xFFEAECE7)
val SurfaceContainerHighestLight = Color(0xFFE4E7E1)
val OutlineLight = Color(0xFF74796E)
val OutlineVariantLight = Color(0xFFC4C8BC)

// Dark theme — same brand green for primary so the accent reads identically
// in either appearance; container tones invert per Material 3 convention.
val PrimaryDark = BrandGreen
val OnPrimaryDark = Color(0xFFFFFFFF)
val PrimaryContainerDark = BrandGreenDeep
val OnPrimaryContainerDark = BrandGreenSoft
val SecondaryDark = BrandGreen
val OnSecondaryDark = Color(0xFFFFFFFF)
val SecondaryContainerDark = BrandGreenDeep
val OnSecondaryContainerDark = BrandGreenSoft
val BackgroundDark = Color(0xFF1A1C1E)
val OnBackgroundDark = Color(0xFFE2E2E6)
val SurfaceDark = Color(0xFF1A1C1E)
val OnSurfaceDark = Color(0xFFE2E2E6)
val SurfaceVariantDark = Color(0xFF43483F)
val OnSurfaceVariantDark = Color(0xFFC4C8BC)
val SurfaceContainerLowestDark = Color(0xFF0F1310)
val SurfaceContainerLowDark = Color(0xFF1A1C1E)
val SurfaceContainerDark = Color(0xFF1F2220)
val SurfaceContainerHighDark = Color(0xFF292B2A)
val SurfaceContainerHighestDark = Color(0xFF343634)
val OutlineDark = Color(0xFF8E938A)
val OutlineVariantDark = Color(0xFF43483F)
