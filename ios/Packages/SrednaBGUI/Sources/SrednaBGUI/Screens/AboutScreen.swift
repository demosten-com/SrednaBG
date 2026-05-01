// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGUI

import SwiftUI

/// Standalone About route. Settings already shows the same content inline,
/// but this screen is what we link to from a future tap-version-7-times
/// debug menu.
public struct AboutScreen: View {
    public let appVersion: String

    public init(appVersion: String = "0.1.0") {
        self.appVersion = appVersion
    }

    public var body: some View {
        Form {
            Section(L10n.aboutTitle) {
                LabeledContent(L10n.aboutTitle, value: String(format: L10n.aboutVersion, appVersion))
                Text(L10n.aboutLicense)
                Text(L10n.aboutAttribution)
                Text(L10n.aboutZoneData)
            }
        }
        .navigationTitle(L10n.aboutTitle)
    }
}
