// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation
import os

/// Structured `os_log` emitters consumed by the QA harness
/// (`qa/devices/ios_log.py`).
///
/// The harness reads these lines off `xcrun simctl spawn booted log stream
/// --predicate 'subsystem == "com.demosten.srednabg"' --style ndjson` and
/// runs the same regex parsers it uses for Android logcat. The line bodies
/// MUST match the regex patterns in `qa/parsers.py` exactly — adding/renaming
/// a field here without updating the parser breaks the smoke suite's
/// self-test loudly (this is the intended tripwire).
///
/// `.public` privacy markers are required because `--style ndjson` honors
/// the Logger redaction system; without them, dynamic values render as
/// `<private>` and the parser can't recover lat/lng/etc.
public enum QALog {

    public static let subsystem = "com.demosten.srednabg"

    /// Location updates + GPS interval changes + zones-loaded counts.
    /// Matches Android's `SrednaBG.Loc` tag.
    public static let location = Logger(subsystem: subsystem, category: "SrednaBG.Loc")

    /// Zone state transitions + TTS speak events.
    /// Matches Android's `SrednaBG.TTS` tag.
    public static let tts = Logger(subsystem: subsystem, category: "SrednaBG.TTS")

    /// Debug sync surface — emitted by `DebugSyncHook`. Matches Android's
    /// `DebugSync` tag.
    public static let sync = Logger(subsystem: subsystem, category: "DebugSync")

    /// Debug settings surface — emitted by the URL scheme dispatcher when a
    /// setting is flipped from outside the app. Matches Android's
    /// `DebugSettings` tag.
    public static let settings = Logger(subsystem: subsystem, category: "DebugSettings")
}
