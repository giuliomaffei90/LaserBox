import SwiftUI

@main
struct LaserBoxApp: App {
    var body: some Scene {
        Window("LaserBox", id: "main") {
            ContentView()
                .frame(minWidth: 900, minHeight: 560)
        }
        .defaultSize(width: 1575, height: 970)
        .commands {
            SidebarCommands()
            InspectorCommands()
            BoxCommands()
        }
    }
}

struct BoxActions {
    var exportSVG: (() -> Void)?  // nil = disabled
    var exportDXF: (() -> Void)?
    var reset: (() -> Void)?
}

extension FocusedValues {
    @Entry var boxActions: BoxActions?
}

struct BoxCommands: Commands {
    @FocusedValue(\.boxActions) private var actions

    var body: some Commands {
        CommandGroup(replacing: .importExport) {
            Button("Export SVG…") { actions?.exportSVG?() }
                .keyboardShortcut("e")
                .disabled(actions?.exportSVG == nil)
            Button("Export DXF…") { actions?.exportDXF?() }
                .keyboardShortcut("e", modifiers: [.command, .shift])
                .disabled(actions?.exportDXF == nil)
        }
        CommandGroup(after: .pasteboard) {
            Divider()
            Button("Reset to Defaults") { actions?.reset?() }
                .disabled(actions?.reset == nil)
        }
    }
}

extension View {
    /// Tinted Liquid Glass for the one primary toolbar action; a bordered prominent button before macOS 26.
    @ViewBuilder func prominentButton() -> some View {
        if #available(macOS 26, *) { buttonStyle(.glassProminent) } else { buttonStyle(.borderedProminent) }
    }
}

/// A gap between toolbar groups on macOS 26; older toolbars have no glass groups to separate.
struct ToolbarGap: ToolbarContent {
    var body: some ToolbarContent {
        if #available(macOS 26, *) { ToolbarSpacer(.fixed) }
    }
}

extension ToolbarContent {
    /// Items without the shared glass capsule (e.g. a spinner); older systems have no capsule anyway.
    @ToolbarContentBuilder func withoutSharedBackground() -> some ToolbarContent {
        if #available(macOS 26, *) { sharedBackgroundVisibility(.hidden) } else { self }
    }
}
