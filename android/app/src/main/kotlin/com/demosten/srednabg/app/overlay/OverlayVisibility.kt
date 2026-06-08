// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.overlay

/**
 * Pure decision for whether the floating system overlay should currently be on
 * screen. Kept side-effect-free so it can be unit-tested without Android — the
 * service `combine`s the four inputs and feeds them here.
 *
 * @param enabled          user setting `overlay_enabled`
 * @param canDrawOverlays  `Settings.canDrawOverlays` (the special permission)
 * @param tracking         a foreground tracking session is active
 * @param appInBackground  our own UI is NOT in the foreground — chat-head
 *                         convention is to hide the overlay while the user is
 *                         inside SrednaBG itself, and show it over other apps.
 */
fun shouldShowOverlay(
    enabled: Boolean,
    canDrawOverlays: Boolean,
    tracking: Boolean,
    appInBackground: Boolean,
): Boolean = enabled && canDrawOverlays && tracking && appInBackground
