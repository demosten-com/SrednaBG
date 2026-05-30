// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation
import SrednaBGCore
import ZIPFoundation

public enum OfflineMapInstallerError: Error, Sendable {
    case missingStyle
    case missingMbtiles
    case zipExtractFailed(any Error & Sendable)
}

/// Manages the on-disk MapLibre bundle (`style-light.json` / `style-dark.json`,
/// `bulgaria.mbtiles`, `fonts/`, optional `sprite.*`, `version.json`). Mirrors the Android
/// `MapRepository.kt` placeholder rewrite + atomic-swap pipeline.
///
/// Layout under `rootDir`:
///   `rootDir/map/`            — live, served to MapLibre
///   `rootDir/map.staging/`    — extracted download awaiting verify+swap
///   `rootDir/map.old/`        — previous live, cleaned up on success
public actor OfflineMapInstaller {

    public struct Layout: Sendable {
        public let mapDir: URL
        public let stagingDir: URL
        public let backupDir: URL

        public init(rootDir: URL) {
            self.mapDir = rootDir.appendingPathComponent("map")
            self.stagingDir = rootDir.appendingPathComponent("map.staging")
            self.backupDir = rootDir.appendingPathComponent("map.old")
        }

        public func styleURL(for theme: MapTheme) -> URL {
            mapDir.appendingPathComponent(Self.styleFileName(for: theme))
        }
        public var mbtilesURL: URL { mapDir.appendingPathComponent("bulgaria.mbtiles") }
        public var fontsURL: URL { mapDir.appendingPathComponent("fonts") }
        public var spriteBaseURL: URL { mapDir.appendingPathComponent("sprite") }
        public var versionURL: URL { mapDir.appendingPathComponent("version.json") }

        public static let styleFileNames: [String] = MapTheme.allCases.map(styleFileName(for:))

        public static func styleFileName(for theme: MapTheme) -> String {
            switch theme {
            case .light: return "style-light.json"
            case .dark: return "style-dark.json"
            }
        }
    }

    public nonisolated let layout: Layout

    public init(rootDir: URL) {
        self.layout = Layout(rootDir: rootDir)
    }

    /// True when the live `map/` dir contains every required style file
    /// (`style-light.json`, `style-dark.json`) and `bulgaria.mbtiles`. The
    /// MapLibre view should fall back to a network style URL until this
    /// returns true.
    public func isInstalled() -> Bool {
        let fm = FileManager.default
        for theme in MapTheme.allCases where !fm.fileExists(atPath: layout.styleURL(for: theme).path) {
            return false
        }
        return fm.fileExists(atPath: layout.mbtilesURL.path)
    }

    /// `file://` URL of the on-disk style for MapLibre. Nil until `install`
    /// completes successfully.
    public func localStyleURL(for theme: MapTheme) -> URL? {
        isInstalled() ? layout.styleURL(for: theme) : nil
    }

    /// Map hash recorded in the live `version.json`. Compare against
    /// `/api/version`'s `map_hash` to decide whether to re-download.
    public func installedMapHash() -> String? {
        guard FileManager.default.fileExists(atPath: layout.versionURL.path) else { return nil }
        do {
            let data = try Data(contentsOf: layout.versionURL)
            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            return json?["map_hash"] as? String
        } catch {
            return nil
        }
    }

    /// First-launch bootstrap: copy the in-app bundled `OfflineMap/` directory
    /// into our managed `map/` dir. The style files are kept as raw placeholder
    /// templates (`{MBTILES_URI}` / `{GLYPHS_URI}` / `{SPRITE_URI}`) so the
    /// runtime rewriter can substitute the current data container's absolute
    /// paths on every launch — iOS relocates the sandbox container on reinstall,
    /// OS restore, and some simulator rotations, and paths baked in at install
    /// time would point to a container UUID that no longer exists.
    ///
    /// When an existing style file has no placeholders (old binary that
    /// rewrote them at install time), replace it from the bundle so the
    /// runtime rewriter has something to work with.
    public func installFromBundle(_ bundleSourceDir: URL) async throws {
        let fm = FileManager.default
        guard fm.fileExists(atPath: bundleSourceDir.path) else { return }

        if !isInstalled() {
            try fm.createDirectory(at: layout.mapDir, withIntermediateDirectories: true)
            try copyTree(from: bundleSourceDir, to: layout.mapDir, fm: fm)
            return
        }

        // Migration: pre-fix installs rewrote the style files to absolute paths.
        // Detect by absence of the placeholder markers and refresh every
        // bundled style file from the template so the container-relocation
        // bug stops biting. Loops over both light and dark variants because
        // a partial install (one rewritten, one not) is still corrupt.
        for theme in MapTheme.allCases {
            let installedStyleURL = layout.styleURL(for: theme)
            let existingStyle = try? String(contentsOf: installedStyleURL, encoding: .utf8)
            let hasPlaceholders = existingStyle.map {
                $0.contains("{GLYPHS_URI}") || $0.contains("{MBTILES_URI}")
            } ?? false
            if hasPlaceholders { continue }

            let bundledStyle = bundleSourceDir
                .appendingPathComponent(Layout.styleFileName(for: theme))
            guard fm.fileExists(atPath: bundledStyle.path) else { continue }
            if fm.fileExists(atPath: installedStyleURL.path) {
                try fm.removeItem(at: installedStyleURL)
            }
            try fm.copyItem(at: bundledStyle, to: installedStyleURL)
        }
    }

    /// Network sync path: the caller has already downloaded the bundle zip;
    /// extract → verify → atomic swap. The style files are left as raw
    /// placeholder templates; see `installFromBundle` for why.
    public func installDownloadedBundle(_ zipURL: URL) async throws {
        let fm = FileManager.default
        // Wipe staging if a previous attempt left it behind.
        if fm.fileExists(atPath: layout.stagingDir.path) {
            try fm.removeItem(at: layout.stagingDir)
        }
        try fm.createDirectory(at: layout.stagingDir, withIntermediateDirectories: true)

        do {
            try fm.unzipItem(at: zipURL, to: layout.stagingDir)
        } catch {
            throw OfflineMapInstallerError.zipExtractFailed(SendableError(error))
        }

        for fileName in Layout.styleFileNames {
            let stagingStyle = layout.stagingDir.appendingPathComponent(fileName)
            guard fm.fileExists(atPath: stagingStyle.path) else { throw OfflineMapInstallerError.missingStyle }
        }
        let stagingTiles = layout.stagingDir.appendingPathComponent("bulgaria.mbtiles")
        guard fm.fileExists(atPath: stagingTiles.path) else { throw OfflineMapInstallerError.missingMbtiles }

        try swapInStaging()
    }

    // MARK: - private helpers

    private func swapInStaging() throws {
        let fm = FileManager.default
        if fm.fileExists(atPath: layout.backupDir.path) {
            try fm.removeItem(at: layout.backupDir)
        }
        if fm.fileExists(atPath: layout.mapDir.path) {
            try fm.moveItem(at: layout.mapDir, to: layout.backupDir)
        }
        do {
            try fm.moveItem(at: layout.stagingDir, to: layout.mapDir)
        } catch {
            // Restore the previous live dir on swap failure.
            if fm.fileExists(atPath: layout.backupDir.path) {
                try? fm.moveItem(at: layout.backupDir, to: layout.mapDir)
            }
            throw error
        }
        if fm.fileExists(atPath: layout.backupDir.path) {
            try? fm.removeItem(at: layout.backupDir)
        }
    }

    private func copyTree(from src: URL, to dst: URL, fm: FileManager) throws {
        try fm.createDirectory(at: dst, withIntermediateDirectories: true)
        let children = try fm.contentsOfDirectory(at: src, includingPropertiesForKeys: [.isDirectoryKey])
        for child in children {
            let childDst = dst.appendingPathComponent(child.lastPathComponent)
            let isDir = (try child.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) ?? false
            if isDir {
                try copyTree(from: child, to: childDst, fm: fm)
            } else {
                if fm.fileExists(atPath: childDst.path) {
                    try fm.removeItem(at: childDst)
                }
                try fm.copyItem(at: child, to: childDst)
            }
        }
    }
}

/// `OfflineMapInstallerError.zipExtractFailed` needs a `Sendable` error;
/// `Error` is not `Sendable` in general. Wrap whatever ZIPFoundation throws.
struct SendableError: Error, Sendable, CustomStringConvertible {
    let description: String
    init(_ underlying: any Error) {
        self.description = String(describing: underlying)
    }
}
