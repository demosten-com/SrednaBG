// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation
import Testing
import ZIPFoundation
@testable import SrednaBGData
import SrednaBGCore

@Suite("OfflineMapInstaller")
struct OfflineMapInstallerTests {

    private func tmpRoot() -> URL {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("SrednaBGMapTests-\(UUID().uuidString)", isDirectory: true)
        try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    /// Build a fake bundled-source dir with placeholder light + dark style
    /// files plus a tiny mbtiles stand-in. The real bundle is ~50 MB; we
    /// only care about the install/rewrite/swap behavior here.
    private func writeFakeBundle(at dir: URL) throws {
        let fm = FileManager.default
        try fm.createDirectory(at: dir, withIntermediateDirectories: true)
        for theme in MapTheme.allCases {
            let style = """
            {
              "version": 8,
              "name": "fake-\(theme.rawValue)",
              "sources": {
                "vector": {"type": "vector", "url": "{MBTILES_URI}"}
              },
              "glyphs": "{GLYPHS_URI}/{fontstack}/{range}.pbf",
              "sprite": "{SPRITE_URI}",
              "layers": []
            }
            """
            let fileName = OfflineMapInstaller.Layout.styleFileName(for: theme)
            try Data(style.utf8).write(to: dir.appendingPathComponent(fileName))
        }
        try Data("fake mbtiles bytes".utf8).write(to: dir.appendingPathComponent("bulgaria.mbtiles"))
        try fm.createDirectory(at: dir.appendingPathComponent("fonts"), withIntermediateDirectories: true)
        try Data(#"{"map_hash":"sha256:bundled"}"#.utf8).write(to: dir.appendingPathComponent("version.json"))
    }

    @Test
    func installFromBundleKeepsStyleAsPlaceholderTemplate() async throws {
        let root = tmpRoot()
        let bundleSource = root.appendingPathComponent("bundle-src")
        try writeFakeBundle(at: bundleSource)

        let installer = OfflineMapInstaller(rootDir: root)
        try await installer.installFromBundle(bundleSource)

        let installed = await installer.isInstalled()
        #expect(installed)

        // Container-relocation hazard: we deliberately do NOT substitute
        // absolute paths at install time. Both style files must stay as the
        // raw template so `StyleRewriter` can re-derive them every launch
        // against the current container.
        for theme in MapTheme.allCases {
            let style = try String(contentsOf: installer.layout.styleURL(for: theme), encoding: .utf8)
            #expect(style.contains("{MBTILES_URI}"))
            #expect(style.contains("{GLYPHS_URI}"))
            #expect(style.contains("{SPRITE_URI}"))
            #expect(!style.contains(installer.layout.mapDir.path))
        }

        let hash = await installer.installedMapHash()
        #expect(hash == "sha256:bundled")

        let localStyle = await installer.localStyleURL(for: .light)
        #expect(localStyle == installer.layout.styleURL(for: .light))
    }

    @Test
    func installFromBundleNoOpsIfAlreadyInstalled() async throws {
        let root = tmpRoot()
        let bundleSource = root.appendingPathComponent("bundle-src")
        try writeFakeBundle(at: bundleSource)

        let installer = OfflineMapInstaller(rootDir: root)
        try await installer.installFromBundle(bundleSource)

        // Second call must not throw or attempt to re-extract.
        try await installer.installFromBundle(bundleSource)
        #expect(await installer.isInstalled())
    }

    @Test
    func installFromBundleRepairsLegacyAbsolutePathStyle() async throws {
        let root = tmpRoot()
        let bundleSource = root.appendingPathComponent("bundle-src")
        try writeFakeBundle(at: bundleSource)

        // Simulate an upgrade from a pre-fix binary: the `map/` dir is
        // fully installed, but every style file has absolute paths pointing
        // at a container UUID that no longer exists (the root cause of
        // "map never loads after reinstall"). The new installer must
        // detect this and swap the template back in for both variants.
        let installer = OfflineMapInstaller(rootDir: root)
        let fm = FileManager.default
        try fm.createDirectory(at: installer.layout.mapDir, withIntermediateDirectories: true)
        try Data("fake tiles".utf8).write(to: installer.layout.mbtilesURL)
        let staleStyle = """
        {
          "sources": {"v": {"type": "vector", "url": "mbtiles:///old-uuid/bulgaria.mbtiles"}},
          "glyphs": "file:///old-uuid/fonts/{fontstack}/{range}.pbf"
        }
        """
        for theme in MapTheme.allCases {
            try Data(staleStyle.utf8).write(to: installer.layout.styleURL(for: theme))
        }

        try await installer.installFromBundle(bundleSource)

        for theme in MapTheme.allCases {
            let style = try String(contentsOf: installer.layout.styleURL(for: theme), encoding: .utf8)
            #expect(style.contains("{MBTILES_URI}"))
            #expect(style.contains("{GLYPHS_URI}"))
            #expect(!style.contains("/old-uuid/"))
        }
    }

    @Test
    func installDownloadedBundleAtomicallySwapsLiveDir() async throws {
        let root = tmpRoot()

        // Pre-install an "old" version so we can verify it gets replaced.
        let oldSrc = root.appendingPathComponent("old-src")
        try writeFakeBundle(at: oldSrc)
        let installer = OfflineMapInstaller(rootDir: root)
        try await installer.installFromBundle(oldSrc)

        // Build a downloaded zip with a fresh map_hash + new style content.
        let stagingSrc = root.appendingPathComponent("new-src")
        try writeFakeBundle(at: stagingSrc)
        // Overwrite both bundled style files with a fresh template marker
        // so we can verify the swap brought in the new content.
        for theme in MapTheme.allCases {
            let newStyle = """
            {
              "version": 8,
              "name": "fresh-\(theme.rawValue)",
              "sources": {
                "vector": {"type": "vector", "url": "{MBTILES_URI}"}
              },
              "glyphs": "{GLYPHS_URI}/{fontstack}/{range}.pbf",
              "sprite": "{SPRITE_URI}",
              "layers": []
            }
            """
            let fileName = OfflineMapInstaller.Layout.styleFileName(for: theme)
            try Data(newStyle.utf8).write(to: stagingSrc.appendingPathComponent(fileName))
        }
        try Data(#"{"map_hash":"sha256:fresh"}"#.utf8).write(to: stagingSrc.appendingPathComponent("version.json"))

        let zipURL = root.appendingPathComponent("bundle.zip")
        try FileManager.default.zipItem(at: stagingSrc, to: zipURL, shouldKeepParent: false)

        try await installer.installDownloadedBundle(zipURL)

        // Both freshly-downloaded style files must be on disk as raw
        // templates (container-relocation hazard: see `installFromBundle`).
        // The runtime `StyleRewriter` does substitution.
        for theme in MapTheme.allCases {
            let style = try String(contentsOf: installer.layout.styleURL(for: theme), encoding: .utf8)
            #expect(style.contains("\"name\": \"fresh-\(theme.rawValue)\""))
            #expect(style.contains("{MBTILES_URI}"))
            #expect(style.contains("{GLYPHS_URI}"))
        }
        let hash = await installer.installedMapHash()
        #expect(hash == "sha256:fresh")
    }

    @Test
    func installDownloadedBundleRejectsZipMissingStyleOrTiles() async throws {
        let root = tmpRoot()
        let stagingSrc = root.appendingPathComponent("partial-src")
        try FileManager.default.createDirectory(at: stagingSrc, withIntermediateDirectories: true)
        try Data("only mbtiles".utf8).write(to: stagingSrc.appendingPathComponent("bulgaria.mbtiles"))

        let zipURL = root.appendingPathComponent("partial.zip")
        try FileManager.default.zipItem(at: stagingSrc, to: zipURL, shouldKeepParent: false)

        let installer = OfflineMapInstaller(rootDir: root)
        await #expect(throws: OfflineMapInstallerError.self) {
            try await installer.installDownloadedBundle(zipURL)
        }
        #expect(await installer.isInstalled() == false)
    }
}
