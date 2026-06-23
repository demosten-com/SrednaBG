// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.overlay

import android.content.Context
import android.content.Intent
import android.graphics.PixelFormat
import android.os.Build
import android.util.Log
import android.view.Gravity
import android.view.WindowManager
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.ComposeView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleRegistry
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.ViewModelStoreOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.setViewTreeLifecycleOwner
import androidx.lifecycle.setViewTreeViewModelStoreOwner
import androidx.savedstate.SavedStateRegistry
import androidx.savedstate.SavedStateRegistryController
import androidx.savedstate.SavedStateRegistryOwner
import androidx.savedstate.setViewTreeSavedStateRegistryOwner
import com.demosten.srednabg.app.data.SettingsRepository
import com.demosten.srednabg.app.ui.MainActivity
import com.demosten.srednabg.app.ui.theme.SrednaBGTheme
import com.demosten.srednabg.core.VehicleType
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlin.math.roundToInt

/**
 * Owns the floating system overlay window (a [ComposeView] added to the
 * [WindowManager] at `TYPE_APPLICATION_OVERLAY`). Hosting Compose outside an
 * Activity requires supplying the ViewTree lifecycle / saved-state / view-model
 * owners ourselves (see [OverlayOwner]).
 *
 * Lifetime is bounded by the owning foreground service: [show]/[hide] are
 * idempotent and driven by the service's visibility coroutine. The window is
 * `WRAP_CONTENT`, so the pill⟷chip swap in [OverlayContent] resizes it for free.
 *
 * Not thread-safe — call [show]/[hide] from the main thread (the service does).
 */
class OverlayController(
    private val context: Context,
    private val scope: CoroutineScope,
    private val settingsRepository: SettingsRepository,
) {
    private val windowManager =
        context.getSystemService(Context.WINDOW_SERVICE) as WindowManager

    private var composeView: ComposeView? = null
    private var owner: OverlayOwner? = null
    private val layoutParams = defaultLayoutParams()
    private var positionLoaded = false
    // Desired visibility, so a hide() that arrives while the first show() is still
    // reading the persisted position (below) doesn't get overtaken by the deferred
    // attach() and strand the window.
    private var wantVisible = false

    fun show() {
        wantVisible = true
        if (composeView != null) return
        if (positionLoaded) {
            attach()
            return
        }
        // First show: read the saved position *before* attaching so the window
        // appears at its persisted spot instead of flashing at the default
        // (DEFAULT_X, DEFAULT_Y) and visibly jumping once the async DataStore read
        // returns. `scope` is main-dispatched (it also drives updateViewLayout on
        // drag), so attach()'s addView stays on the main thread.
        scope.launch {
            val x = settingsRepository.overlayPosX.first()
            val y = settingsRepository.overlayPosY.first()
            if (x != SettingsRepository.OVERLAY_POS_UNSET) {
                layoutParams.x = x
                layoutParams.y = y
                // Guard against an off-screen value persisted by an older build
                // that didn't clamp on drag.
                clampToScreen(layoutParams)
            }
            positionLoaded = true
            // hide() may have fired while we were reading — only attach if the
            // overlay is still wanted and not already attached.
            if (wantVisible && composeView == null) attach()
        }
    }

    private fun attach() {
        val lifecycleOwner = OverlayOwner().also { it.onCreate() }
        val view = ComposeView(context).apply {
            setViewTreeLifecycleOwner(lifecycleOwner)
            setViewTreeSavedStateRegistryOwner(lifecycleOwner)
            setViewTreeViewModelStoreOwner(lifecycleOwner)
            setContent {
                SrednaBGTheme {
                    val debug by settingsRepository.debugMaxSpeedOverride
                        .collectAsStateWithLifecycle(initialValue = null)
                    val vehicleSetting by settingsRepository.vehicleType
                        .collectAsStateWithLifecycle(initialValue = SettingsRepository.DEFAULT_VEHICLE_TYPE)
                    OverlayContent(
                        vehicleType = VehicleType.fromSetting(vehicleSetting),
                        debugMaxSpeedOverride = debug,
                        modifier = Modifier
                            .pointerInput(Unit) {
                                detectDragGestures(
                                    onDrag = { change, dragAmount ->
                                        change.consume()
                                        moveBy(dragAmount.x, dragAmount.y)
                                    },
                                    onDragEnd = { persistPosition() },
                                )
                            }
                            .pointerInput(Unit) {
                                detectTapGestures(onTap = { launchApp() })
                            },
                    )
                }
            }
        }
        owner = lifecycleOwner
        composeView = view
        try {
            windowManager.addView(view, layoutParams)
            lifecycleOwner.onResume()
        } catch (e: Exception) {
            // Permission revoked between the gate check and addView, or an OEM
            // quirk — fail soft rather than crash the tracking service. If the
            // throw came *after* addView succeeded (e.g. onResume()), the window
            // is already attached, so try to remove it before we drop our handle
            // — otherwise hide() can never reach it and it's stranded on screen.
            Log.w(TAG, "addView failed; overlay not shown", e)
            runCatching { windowManager.removeViewImmediate(view) }
            composeView = null
            owner = null
        }
    }

    fun hide() {
        wantVisible = false
        val view = composeView ?: return
        try {
            windowManager.removeViewImmediate(view)
        } catch (e: Exception) {
            Log.w(TAG, "removeView failed", e)
        }
        owner?.onDestroy()
        composeView = null
        owner = null
    }

    /**
     * Tapping the overlay brings SrednaBG to the front. That moves the process
     * to foreground, which the service's visibility gate reads as "app in
     * foreground" and hides the overlay — the desired tap-to-open behaviour.
     */
    private fun launchApp() {
        val intent = Intent(context, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)
        context.startActivity(intent)
    }

    private fun moveBy(dx: Float, dy: Float) {
        val params = layoutParams
        params.x += dx.roundToInt()
        params.y += dy.roundToInt()
        clampToScreen(params)
        composeView?.let { windowManager.updateViewLayout(it, params) }
    }

    /**
     * Keep the whole badge on-screen. `FLAG_LAYOUT_NO_LIMITS` lets the window be
     * positioned outside the display, so without this a vigorous drag could fling
     * the overlay fully off-screen — and [persistPosition] would save it there,
     * restoring it invisibly next session. Clamps to the same coordinate space as
     * `gravity = TOP|START` (pixels from the top-left). The view may be unmeasured
     * (width/height 0) on the first restore; clamping to `[0, screen]` is still safe.
     */
    private fun clampToScreen(params: WindowManager.LayoutParams) {
        val (screenW, screenH) = screenSize()
        val viewW = composeView?.width ?: 0
        val viewH = composeView?.height ?: 0
        params.x = params.x.coerceIn(0, (screenW - viewW).coerceAtLeast(0))
        params.y = params.y.coerceIn(0, (screenH - viewH).coerceAtLeast(0))
    }

    private fun screenSize(): Pair<Int, Int> =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val bounds = windowManager.currentWindowMetrics.bounds
            bounds.width() to bounds.height()
        } else {
            @Suppress("DEPRECATION")
            val metrics = context.resources.displayMetrics
            metrics.widthPixels to metrics.heightPixels
        }

    private fun persistPosition() {
        val x = layoutParams.x
        val y = layoutParams.y
        scope.launch { settingsRepository.setOverlayPosition(x, y) }
    }

    private fun defaultLayoutParams() = WindowManager.LayoutParams(
        WindowManager.LayoutParams.WRAP_CONTENT,
        WindowManager.LayoutParams.WRAP_CONTENT,
        // minSdk 26 — TYPE_APPLICATION_OVERLAY is always available, no fallback.
        WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
        WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
            WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
        PixelFormat.TRANSLUCENT,
    ).apply {
        gravity = Gravity.TOP or Gravity.START
        x = DEFAULT_X
        y = DEFAULT_Y
    }

    /**
     * Minimal lifecycle + saved-state + view-model owner so a [ComposeView] can
     * run outside an Activity. Driven manually: CREATED on attach, RESUMED once
     * added to the window, DESTROYED on teardown.
     */
    private class OverlayOwner : SavedStateRegistryOwner, ViewModelStoreOwner {
        private val lifecycleRegistry = LifecycleRegistry(this)
        private val savedStateController = SavedStateRegistryController.create(this)
        override val viewModelStore = ViewModelStore()
        override val lifecycle: Lifecycle get() = lifecycleRegistry
        override val savedStateRegistry: SavedStateRegistry
            get() = savedStateController.savedStateRegistry

        fun onCreate() {
            savedStateController.performRestore(null)
            lifecycleRegistry.currentState = Lifecycle.State.CREATED
        }

        fun onResume() {
            lifecycleRegistry.currentState = Lifecycle.State.RESUMED
        }

        fun onDestroy() {
            lifecycleRegistry.currentState = Lifecycle.State.DESTROYED
            viewModelStore.clear()
        }
    }

    private companion object {
        const val TAG = "SrednaBG.Overlay"
        const val DEFAULT_X = 24
        const val DEFAULT_Y = 120
    }
}
