// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

#if os(iOS)
import Foundation
import os
@preconcurrency import BackgroundTasks

/// Wraps `BGTaskScheduler` for the two periodic syncs:
///
///   * `com.demosten.srednabg.zonesync` — `BGAppRefreshTask` ~6h, any network.
///     Pulls `/api/version`, fetches `/api/zones` only when the hash changed.
///   * `com.demosten.srednabg.mapsync`  — `BGProcessingTask` ~6h, network
///     required. Apple does not expose Wi-Fi-only via `BGProcessingTaskRequest`;
///     gate manually with `NWPathMonitor` inside the handler and reschedule
///     for later if the path is metered.
///
/// `register(...)` must be called from `application(_:didFinishLaunching...)`
/// on the main thread before scenes connect; the handler bodies dispatch into
/// async actors via `Task`.
public enum BackgroundSyncScheduler {
    public static let zoneSyncIdentifier = "com.demosten.srednabg.zonesync"
    public static let mapSyncIdentifier = "com.demosten.srednabg.mapsync"

    /// Sync interval matching the Android `WorkManager` default.
    public static let interval: TimeInterval = 6 * 60 * 60

    public static func register(
        zoneSync: @escaping @Sendable () async -> Void,
        mapSync: @escaping @Sendable () async -> Void
    ) {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: zoneSyncIdentifier, using: nil) { task in
            handle(task: task, work: zoneSync, reschedule: scheduleZoneSync)
        }
        BGTaskScheduler.shared.register(forTaskWithIdentifier: mapSyncIdentifier, using: nil) { task in
            handle(task: task, work: mapSync, reschedule: scheduleMapSync)
        }
    }

    public static func scheduleZoneSync() {
        let request = BGAppRefreshTaskRequest(identifier: zoneSyncIdentifier)
        request.earliestBeginDate = Date(timeIntervalSinceNow: interval)
        try? BGTaskScheduler.shared.submit(request)
    }

    /// Cancels any pending zone-sync request — used when the user turns off the
    /// "Automatic zone updates" setting. Mirrors the Android
    /// `WorkManager.cancelUniqueWork("zone_sync")`.
    public static func cancelZoneSync() {
        BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: zoneSyncIdentifier)
    }

    public static func scheduleMapSync() {
        let request = BGProcessingTaskRequest(identifier: mapSyncIdentifier)
        request.requiresNetworkConnectivity = true
        request.requiresExternalPower = false
        request.earliestBeginDate = Date(timeIntervalSinceNow: interval)
        try? BGTaskScheduler.shared.submit(request)
    }

    private static func handle(
        task: BGTask,
        work: @escaping @Sendable () async -> Void,
        reschedule: @escaping @Sendable () -> Void
    ) {
        // `setTaskCompleted` must be called exactly once: the job's success
        // path races the expiration handler when iOS expires us just as
        // `work()` finishes. Whoever flips the flag first completes the task.
        let completed = OSAllocatedUnfairLock(initialState: false)
        let completeOnce: @Sendable (Bool) -> Void = { success in
            let isFirst = completed.withLock { done in
                if done { return false }
                done = true
                return true
            }
            if isFirst { task.setTaskCompleted(success: success) }
        }
        let job = Task {
            await work()
            completeOnce(true)
        }
        task.expirationHandler = {
            job.cancel()
            completeOnce(false)
        }
        // Always re-arm before returning — otherwise iOS won't fire us again.
        reschedule()
    }
}
#endif
