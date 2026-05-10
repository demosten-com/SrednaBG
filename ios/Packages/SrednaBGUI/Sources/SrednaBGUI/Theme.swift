// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGUI
//
// `Theme` and `statusSwiftUIColor(_:)` live in `SrednaBGTheme` so the widget
// extension can share the palette without pulling in MapLibre. We re-export
// the module here so existing `import SrednaBGUI` callers keep compiling
// without per-file changes.

@_exported import SrednaBGTheme
