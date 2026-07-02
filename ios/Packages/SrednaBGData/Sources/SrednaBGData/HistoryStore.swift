// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation
import SwiftData

/// `@MainActor` persistence facade for the History tab, wrapping a SwiftData
/// `ModelContainer` + `ModelContext`. Mirrors Android's `HistoryRepository`.
///
/// `@MainActor` matches `ZoneTrackingService`'s isolation (the one write site)
/// and sidesteps the `ModelContext` cross-isolation awkwardness that the
/// `ZoneStore` doc-comment warns about — the container is built once and the
/// store injected everywhere it's needed.
@MainActor
public final class HistoryStore {

    /// Exposed so the History UI can attach it via `.modelContainer(_:)` and
    /// read records reactively with `@Query` against the same `mainContext`
    /// this store writes to.
    public let container: ModelContainer
    private var context: ModelContext { container.mainContext }

    /// Build a store backed by the app's on-disk SwiftData store, degrading
    /// through progressively simpler containers so History — which is
    /// non-critical, best-effort local data — can never take the app process
    /// down at launch:
    ///   1. the on-disk store (preferred),
    ///   2. an in-memory store with the real schema (persists nothing this
    ///      session, but History still works) if the on-disk store is corrupt,
    ///   3. a minimal empty-schema in-memory container as a last resort, which
    ///      has no store file and no models to migrate — so it has no realistic
    ///      failure mode and History simply renders an empty list.
    public init() {
        let schema = Schema([ZoneTraversalRecord.self])
        if let persistent = try? ModelContainer(
            for: schema,
            configurations: [ModelConfiguration(schema: schema, isStoredInMemoryOnly: false)]
        ) {
            self.container = persistent
        } else if let memory = try? ModelContainer(
            for: schema,
            configurations: [ModelConfiguration(schema: schema, isStoredInMemoryOnly: true)]
        ) {
            self.container = memory
        } else {
            self.container = Self.emptyInMemoryContainer()
        }
    }

    /// The minimal container SwiftData can build: no models, in-memory only.
    /// Reached only when both the on-disk and real-schema in-memory containers
    /// fail — an empty in-memory schema touches no disk and migrates nothing, so
    /// this is as close to non-failing as `ModelContainer` gets. The force-try is
    /// the tail of the non-crashing fallback chain above, not the primary path.
    private static func emptyInMemoryContainer() -> ModelContainer {
        // swiftlint:disable:next force_try
        try! ModelContainer(
            for: Schema([]),
            configurations: [ModelConfiguration(isStoredInMemoryOnly: true)]
        )
    }

    /// Test / preview seam: inject an explicit container (e.g. in-memory).
    public init(container: ModelContainer) {
        self.container = container
    }

    /// Convenience for tests: an in-memory-only store.
    public static func inMemory() throws -> HistoryStore {
        let schema = Schema([ZoneTraversalRecord.self])
        let container = try ModelContainer(
            for: schema,
            configurations: [ModelConfiguration(schema: schema, isStoredInMemoryOnly: true)]
        )
        return HistoryStore(container: container)
    }

    public func insert(_ record: ZoneTraversalRecord) {
        context.insert(record)
        try? context.save()
    }

    /// Insert many records with a single `save()` — the bulk path for the QA
    /// seeder, which otherwise issues one write per row. Ordinary recording uses
    /// `insert(_:)` (one record at a time).
    public func insertAll(_ records: [ZoneTraversalRecord]) {
        for record in records { context.insert(record) }
        try? context.save()
    }

    /// All records, most-recently-exited first — drives the History list.
    public func fetchAll() -> [ZoneTraversalRecord] {
        let descriptor = FetchDescriptor<ZoneTraversalRecord>(
            sortBy: [SortDescriptor(\.exitTimeMs, order: .reverse)]
        )
        return (try? context.fetch(descriptor)) ?? []
    }

    public func fetchById(_ id: String) -> ZoneTraversalRecord? {
        let descriptor = FetchDescriptor<ZoneTraversalRecord>(
            predicate: #Predicate { $0.id == id }
        )
        return (try? context.fetch(descriptor))?.first
    }

    /// Most-recently-exited record — backs the QA `DUMP_HISTORY` summary
    /// (Android `HistoryRepository.latest()`).
    public func fetchLatest() -> ZoneTraversalRecord? {
        var descriptor = FetchDescriptor<ZoneTraversalRecord>(
            sortBy: [SortDescriptor(\.exitTimeMs, order: .reverse)]
        )
        descriptor.fetchLimit = 1
        return (try? context.fetch(descriptor))?.first
    }

    /// Total stored traversals — backs the QA `DUMP_HISTORY` count
    /// (Android `HistoryRepository.count()`).
    public func count() -> Int {
        (try? context.fetchCount(FetchDescriptor<ZoneTraversalRecord>())) ?? 0
    }

    /// Delete every record that exited before `olderThanMs`.
    public func prune(olderThanMs cutoffMs: Int64) {
        let descriptor = FetchDescriptor<ZoneTraversalRecord>(
            predicate: #Predicate { $0.exitTimeMs < cutoffMs }
        )
        guard let stale = try? context.fetch(descriptor) else { return }
        for record in stale { context.delete(record) }
        try? context.save()
    }

    public func deleteAll() {
        try? context.delete(model: ZoneTraversalRecord.self)
        try? context.save()
    }

    /// Apply a retention window: `none` clears everything, any other keeps
    /// records that exited within the last `months × APPROX_MONTH_MS`.
    /// `nowMs` is injectable so tests / the app can pin a clock. Mirrors
    /// Android `HistoryRepository.prune(retention, nowMs)`.
    public func applyRetention(_ retention: HistoryRetention, nowMs: Int64) {
        guard retention.isRecording else {
            deleteAll()
            return
        }
        let cutoff = nowMs - Int64(retention.months) * HistoryRetention.approxMonthMs
        prune(olderThanMs: cutoff)
    }
}
