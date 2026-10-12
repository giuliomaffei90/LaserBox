import SwiftUI
import UniformTypeIdentifiers
import WebKit

extension UTType {
    static let dxf = UTType(importedAs: "com.autodesk.dxf")
}

struct CutFile: FileDocument {
    static let readableContentTypes: [UTType] = [.svg, .dxf]
    var data: Data
    init(data: Data) { self.data = data }
    init(configuration: ReadConfiguration) throws { data = configuration.file.regularFileContents ?? Data() }
    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper { FileWrapper(regularFileWithContents: data) }
}

/// One box type: parameters in the inspector, live drawing in the middle.
struct EditorView: View {
    let model: BoxModel
    let generator: GeneratorInfo
    @State private var showInspector = true
    @State private var showInfo = false
    @State private var exportFile: CutFile?
    @State private var exportType: UTType = .svg
    @State private var exportError: String?

    var body: some View {
        preview
            .inspector(isPresented: $showInspector) {
                ParametersForm(model: model)
                    .inspectorColumnWidth(min: 300, ideal: 380, max: 560)
            }
            .navigationTitle(generator.title)
            .navigationSubtitle(generator.doc)
            .toolbar { toolbar }
            .task(id: generator.name) { model.selection = generator.name }
            .focusedSceneValue(\.boxActions, boxActions)
            .fileExporter(
                isPresented: Binding { exportFile != nil } set: { if !$0 { exportFile = nil } },
                document: exportFile, contentType: exportType,
                defaultFilename: generator.title
            ) { result in
                if case .failure(let error) = result { exportError = error.localizedDescription }
            }
            .alert("Couldn’t Export the File", isPresented: Binding { exportError != nil } set: { if !$0 { exportError = nil } }) {
            } message: {
                Text(exportError ?? "")
            }
    }

    private var ready: Bool { model.spec?.name == generator.name }

    private var boxActions: BoxActions {
        let model = model
        return BoxActions(
            exportSVG: ready ? { export(.svg) } : nil,
            exportDXF: ready ? { export(.dxf) } : nil,
            reset: ready && model.hasOverrides ? { model.resetToDefaults() } : nil)
    }

    @ViewBuilder private var preview: some View {
        if let svg = model.svg, ready {
            SVGPreview(svg: svg)
                .overlay(alignment: .top) {
                    if let error = model.error {
                        Label(error, systemImage: "exclamationmark.triangle.fill")
                            .padding(.horizontal, 12).padding(.vertical, 8)
                            .background(.regularMaterial, in: .capsule)
                            .padding()
                    }
                }
        } else if let error = model.error {
            ContentUnavailableView("Can’t Draw This Box", systemImage: "exclamationmark.triangle", description: Text(error))
        } else {
            ProgressView()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    @ToolbarContentBuilder private var toolbar: some ToolbarContent {
        if model.isRendering {
            ToolbarItem {
                ProgressView().controlSize(.small)
            }
            .withoutSharedBackground()
        }
        ToolbarItem {
            Button {
                showInfo = true
            } label: {
                Label("About This Box", systemImage: "info.circle")
            }
            .help("About this box")
            .popover(isPresented: $showInfo, arrowEdge: .bottom) {
                BoxInfo(generator: generator, html: model.spec?.description ?? "")
            }
        }
        ToolbarGap()
        ToolbarItem {
            Menu("Export") {
                Button("SVG…") { export(.svg) }
                Button("DXF…") { export(.dxf) }
            }
            .prominentButton()
            .disabled(!ready)
            .help("Export the cut file")
        }
        ToolbarGap()
        ToolbarItem {
            Button {
                showInspector.toggle()
            } label: {
                Label("Parameters", systemImage: "sidebar.trailing")
            }
            .help(showInspector ? Text("Hide the parameters") : Text("Show the parameters"))
        }
    }

    private func export(_ type: UTType) {
        Task {
            do {
                let data = try await model.export(format: type == .dxf ? "dxf" : "svg")
                exportType = type
                exportFile = CutFile(data: data)
            } catch {
                exportError = error.localizedDescription
            }
        }
    }
}

struct ParametersForm: View {
    let model: BoxModel
    @State private var expanded: Set<String> = []

    var body: some View {
        if let spec = model.spec {
            Form {
                ForEach(spec.groups) { group in
                    if group.advanced {
                        Section(group.title, isExpanded: Binding {
                            expanded.contains(group.id)
                        } set: {
                            if $0 { expanded.insert(group.id) } else { expanded.remove(group.id) }
                        }) {
                            rows(group)
                        }
                    } else {
                        Section(group.title) { rows(group) }
                    }
                }
                Section {
                    Button("Reset to Defaults", action: model.resetToDefaults)
                        .disabled(!model.hasOverrides)
                }
            }
            .formStyle(.grouped)
            .id(spec.name)  // fresh scroll position and collapsed sections per box type
        } else {
            ProgressView()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private func rows(_ group: ArgGroup) -> some View {
        ForEach(group.args) { arg in
            let text = Binding { model.value(arg) } set: { model.set($0, for: arg) }
            switch arg.kind {
            case "bool":
                Toggle(isOn: Binding { text.wrappedValue == "1" } set: { text.wrappedValue = $0 ? "1" : "0" }) {
                    label(arg)
                }
            case "choice":
                Picker(selection: text) {
                    ForEach(arg.choices ?? [], id: \.value) { Text($0.label).tag($0.value) }
                } label: {
                    label(arg)
                }
            case "multiline":
                VStack(alignment: .leading) {
                    label(arg)
                    TextEditor(text: text)
                        .font(.body.monospaced())
                        .frame(minHeight: 160)
                }
            default:
                TextField(text: text) { label(arg) }
                    .multilineTextAlignment(.trailing)
            }
        }
    }

    @ViewBuilder private func label(_ arg: Arg) -> some View {
        Text(arg.label.prefix(1).uppercased() + arg.label.dropFirst())
        if !arg.help.isEmpty { Text(arg.help) }
    }
}

/// Photo, summary and the long description from boxes.py.
struct BoxInfo: View {
    let generator: GeneratorInfo
    let html: String

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Color.clear
                .frame(height: 260)
                .overlay { SampleImage(name: generator.name) }
                .clipShape(.rect(cornerRadius: 10))
            Text(generator.title).font(.title3.bold())
            Text(generator.doc).foregroundStyle(.secondary)
            if !html.isEmpty {
                HTMLView(html: html)
                    .frame(minHeight: 220)
            }
        }
        .padding()
        .frame(width: 440)
        .frame(maxHeight: 640)
    }
}

/// Renders the description HTML; its pictures point at Runtime/samples.
struct HTMLView: NSViewRepresentable {
    let html: String

    func makeNSView(context: Context) -> WKWebView {
        let view = WKWebView()
        view.setValue(false, forKey: "drawsBackground")
        return view
    }

    func updateNSView(_ view: WKWebView, context: Context) {
        view.loadHTMLString("""
            <html><head><meta charset="utf-8"><style>
            :root { color-scheme: light dark; }
            body { font: -apple-system-body; margin: 0; }
            img { max-width: 100%; border-radius: 8px; }
            a { color: -apple-system-control-accent; }
            </style></head><body>\(html)</body></html>
            """, baseURL: Bundle.main.resourceURL!.appending(path: "Runtime/"))
    }
}

/// Shows the SVG on white "paper". Updates replace the drawing in place, so zoom (pinch) and scroll survive.
struct SVGPreview: NSViewRepresentable {
    let svg: String

    func makeNSView(context: Context) -> WKWebView {
        let view = WKWebView()
        view.allowsMagnification = true
        view.navigationDelegate = context.coordinator
        view.loadHTMLString("""
            <html><head><style>
            html, body { margin: 0; height: 100%; background: #e9e9ec; }
            @media (prefers-color-scheme: dark) { html, body { background: #2a2a2d; } }
            #paper { box-sizing: border-box; height: 100%; padding: 24px; display: flex; }
            svg { flex: 1; width: 100%; height: 100%; background: white; box-shadow: 0 1px 4px rgba(0,0,0,.25); }
            </style></head><body><div id="paper"></div></body></html>
            """, baseURL: nil)
        return view
    }

    func updateNSView(_ view: WKWebView, context: Context) {
        context.coordinator.show(svg, in: view)
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    final class Coordinator: NSObject, WKNavigationDelegate {
        private var loaded = false
        private var pending: String?

        func show(_ svg: String, in view: WKWebView) {
            pending = svg
            guard loaded else { return }
            view.callAsyncJavaScript("document.getElementById('paper').innerHTML = svg", arguments: ["svg": svg], in: nil, in: .page)
        }

        func webView(_ view: WKWebView, didFinish navigation: WKNavigation!) {
            loaded = true
            if let pending { show(pending, in: view) }
        }
    }
}
