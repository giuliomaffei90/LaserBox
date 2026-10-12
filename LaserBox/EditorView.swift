import SceneKit
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
    @State private var materialID = SheetMaterial.standard.id  // every box opens in MDF
    @AppStorage("showsDecorations") private var showsDecorations = true

    var body: some View {
        preview
            .inspector(isPresented: $showInspector) {
                ParametersForm(model: model)
                    .inspectorColumnWidth(min: 300, ideal: 380, max: 560)
            }
            .navigationTitle(generator.title)
            .navigationSubtitle(generator.doc)
            .toolbar { toolbar }
            .task(id: generator.name) {
                model.selection = generator.name
                materialID = SheetMaterial.standard.id
            }
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
        if model.showsAssembly, ready {
            Group {
                if let assembly = model.assembly {
                    AssemblyView(assembly: assembly, key: model.assemblyKey,
                                 material: SheetMaterial.named(materialID), decorations: showsDecorations)
                } else if let error = model.assemblyError {
                    ContentUnavailableView("No 3D View for This Box", systemImage: "cube.transparent", description: Text(error))
                } else {
                    ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .overlay(alignment: .top) {
                if let error = model.error {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .padding(.horizontal, 12).padding(.vertical, 8)
                        .background(.regularMaterial, in: .capsule)
                        .padding()
                }
            }
        } else if let svg = model.svg, ready {
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
        ToolbarItemGroup(placement: .principal) {
            Picker("View", selection: Binding { model.showsAssembly } set: { model.showsAssembly = $0 }) {
                Text("Cut Sheet").tag(false)
                Text("Assembled").tag(true)
            }
            .pickerStyle(.segmented)
            .help("Show the cut sheet or the assembled box")
            if model.showsAssembly {
                Toggle(isOn: $showsDecorations) {
                    Label("Decorations", systemImage: "sparkles")
                }
                .toggleStyle(.button)
                .disabled(!(model.assembly?.pieces.contains { $0.decoration != nil } ?? false))
                .help("Show or hide the decorations: what goes in the box, which isn’t cut")
                Picker("Material", selection: $materialID) {
                    ForEach(SheetMaterial.Kind.allCases) { kind in
                        Section(kind.title) {
                            ForEach(SheetMaterial.all.filter { $0.kind == kind }) { material in
                                Label { Text(material.name) } icon: { Image(nsImage: material.swatch) }
                                    .tag(material.id)
                            }
                        }
                    }
                }
                .pickerStyle(.menu)
                .labelStyle(.titleAndIcon)
                .fixedSize()
                .help("Choose the material for the 3D view")
            }
        }
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

/// Illustration, summary, the long description from boxes.py and the web site's photo of a real one.
struct BoxInfo: View {
    let generator: GeneratorInfo
    let html: String

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Color.clear
                    .frame(height: 260)
                    .overlay { SampleImage(name: generator.name) }
                    .clipShape(.rect(cornerRadius: 10))
                Text(generator.title).font(.title3.bold())
                Text(generator.doc).foregroundStyle(.secondary)
                if !html.isEmpty {
                    HTMLView(html: html)
                        .frame(height: 220)
                }
                if SampleImage.hasPhoto(generator.name) {
                    Text("Made by someone").font(.headline).padding(.top, 4)
                    Color.clear
                        .frame(height: 260)
                        .overlay { SampleImage(name: generator.name, photo: true) }
                        .clipShape(.rect(cornerRadius: 10))
                }
            }
            .padding()
        }
        .frame(width: 440)
        .frame(maxHeight: 700)
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

/// The assembled box: every piece extruded and placed in the chosen material, plus its decorations.
/// `interactive` gives the full orbit/zoom camera; otherwise `yaw`/`pitch` turn the box.
struct AssemblyView: NSViewRepresentable {
    let assembly: Assembly
    let key: String          // changes when the geometry changes
    var material = SheetMaterial.standard
    var decorations = true
    var interactive = true
    var yaw: CGFloat = 0
    var pitch: CGFloat = 0

    func makeNSView(context: Context) -> SCNView {
        let view = SCNView()
        view.allowsCameraControl = interactive
        view.autoenablesDefaultLighting = false
        view.antialiasingMode = .multisampling4X
        view.backgroundColor = .clear
        view.scene = Self.makeScene(coordinator: context.coordinator)
        view.pointOfView = context.coordinator.camera
        return view
    }

    func updateNSView(_ view: SCNView, context: Context) {
        let c = context.coordinator
        let key = "\(key)|\(material.id)|\(decorations)"
        if c.key != key {
            c.key = key
            c.spin.childNodes.forEach { $0.removeFromParentNode() }
            let box = SCNNode()
            for piece in assembly.pieces where decorations || piece.decoration == nil {
                box.addChildNode(Self.node(for: piece, material: material))
            }
            let (minV, maxV) = box.boundingBox
            box.position = SCNVector3(-(minV.x + maxV.x) / 2, -(minV.y + maxV.y) / 2, -(minV.z + maxV.z) / 2)
            let tilt = SCNNode()           // boxes.py is z-up, SceneKit y-up
            tilt.eulerAngles.x = -.pi / 2
            tilt.addChildNode(box)
            c.spin.addChildNode(tilt)
            let dx = maxV.x - minV.x, dy = maxV.y - minV.y, dz = maxV.z - minV.z
            let size = sqrt(dx * dx + dy * dy + dz * dz)   // the diagonal: fits from any angle
            if abs(size - c.size) > 0.5 || !interactive {
                c.size = size
                c.frame(size: size, interactive: interactive)
                view.pointOfView = c.camera
            }
        }
        c.spin.eulerAngles = SCNVector3(pitch, yaw, 0)
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    final class Coordinator {
        var key = ""
        var size: CGFloat = 0
        let spin = SCNNode()
        let camera = SCNNode()
        let sun = SCNNode()

        func frame(size: CGFloat, interactive: Bool) {
            let cam = camera.camera!
            cam.orthographicScale = Double(size) * (interactive ? 0.6 : 0.54)
            camera.position = SCNVector3(size * 2, size * 1.5, size * 2)
            camera.look(at: SCNVector3Zero)
            cam.zFar = Double(size) * 20
            cam.screenSpaceAmbientOcclusionRadius = Double(size) * 0.05
            let light = sun.light!
            light.orthographicScale = Double(size) * 1.2
            light.zNear = 1; light.zFar = Double(size) * 8   // the shadow map must reach the whole box
            sun.position = SCNVector3(size * 0.9, size * 2.2, size * 1.4)
            sun.look(at: SCNVector3Zero)
        }
    }

    private static func makeScene(coordinator c: Coordinator) -> SCNScene {
        let scene = SCNScene()
        scene.rootNode.addChildNode(c.spin)

        let cam = SCNCamera()
        cam.usesOrthographicProjection = true
        cam.zNear = 1; cam.zFar = 10000
        // Ambient occlusion darkens the joints and the inside corners.
        cam.screenSpaceAmbientOcclusionIntensity = 2.2
        cam.screenSpaceAmbientOcclusionBias = 0.3
        cam.screenSpaceAmbientOcclusionDepthThreshold = 2
        cam.screenSpaceAmbientOcclusionNormalThreshold = 0.1
        c.camera.camera = cam
        scene.rootNode.addChildNode(c.camera)

        let sun = SCNLight()
        sun.type = .directional; sun.intensity = 850
        sun.castsShadow = true; sun.shadowMode = .deferred; sun.shadowSampleCount = 32
        sun.shadowMapSize = CGSize(width: 2048, height: 2048)
        sun.shadowRadius = 5; sun.shadowColor = NSColor(white: 0, alpha: 0.55)
        sun.automaticallyAdjustsShadowProjection = false
        c.sun.light = sun
        scene.rootNode.addChildNode(c.sun)

        let fill = SCNNode()
        fill.light = SCNLight(); fill.light!.type = .directional; fill.light!.intensity = 250
        fill.position = SCNVector3(-1, 0.5, -1); fill.look(at: SCNVector3Zero)
        scene.rootNode.addChildNode(fill)

        let ambient = SCNNode()
        ambient.light = SCNLight(); ambient.light!.type = .ambient; ambient.light!.intensity = 330
        scene.rootNode.addChildNode(ambient)
        return scene
    }

    /// Decoration kinds (assembly.py) and their look.
    private static let decorationMaterials = [
        "paper": SheetMaterial.surface(NSColor(red: 0.99, green: 0.95, blue: 0.62, alpha: 1), roughness: 0.95, edge: "float3(0.85)"),
    ]

    /// SCNShape extrudes a flat path along z, centred; the path's even-odd rule turns inner rings into holes.
    private static func node(for piece: Piece, material: SheetMaterial) -> SCNNode {
        let path = NSBezierPath()
        path.windingRule = .evenOdd
        for ring in piece.rings where ring.count >= 3 {
            path.move(to: NSPoint(x: ring[0][0], y: ring[0][1]))
            for p in ring.dropFirst() { path.line(to: NSPoint(x: p[0], y: p[1])) }
            path.close()
        }
        path.flatness = 0.2
        let shape = SCNShape(path: path, extrusionDepth: CGFloat(piece.t))
        let node = SCNNode(geometry: shape)
        if let kind = piece.decoration {
            shape.materials = [decorationMaterials[kind] ?? material.scn]
        } else {
            shape.materials = [material.scn]
            if material.kind == .clearAcrylic {  // SceneKit ignores the material's transparency with these shaders
                node.opacity = 0.45
                node.castsShadow = false
            }
        }
        let u = SCNVector3(piece.u[0], piece.u[1], piece.u[2])
        let v = SCNVector3(piece.v[0], piece.v[1], piece.v[2])
        let s = CGFloat(piece.side)
        let n = SCNVector3(s * (u.y * v.z - u.z * v.y), s * (u.z * v.x - u.x * v.z), s * (u.x * v.y - u.y * v.x))
        let o = piece.origin
        let half = CGFloat(piece.t) / 2
        node.transform = SCNMatrix4(
            m11: u.x, m12: u.y, m13: u.z, m14: 0,
            m21: v.x, m22: v.y, m23: v.z, m24: 0,
            m31: n.x, m32: n.y, m33: n.z, m34: 0,
            m41: CGFloat(o[0]) + n.x * half, m42: CGFloat(o[1]) + n.y * half, m43: CGFloat(o[2]) + n.z * half, m44: 1)
        return node
    }
}

/// What the box is cut from, as the 3D view shows it.
struct SheetMaterial: Identifiable {
    enum Kind: CaseIterable, Identifiable {
        case wood, acrylic, clearAcrylic
        var id: Self { self }
        var title: LocalizedStringKey {
            switch self {
            case .wood: "Wood"
            case .acrylic: "Acrylic"
            case .clearAcrylic: "Transparent Acrylic"
            }
        }
    }

    let id: String
    let name: LocalizedStringKey
    let kind: Kind
    let color: NSColor

    private init(_ id: String, _ name: LocalizedStringKey, _ kind: Kind, _ r: Double, _ g: Double, _ b: Double) {
        self.id = id; self.name = name; self.kind = kind
        color = NSColor(red: r, green: g, blue: b, alpha: 1)
    }

    static let all: [SheetMaterial] = [
        .init("birch", "Birch Plywood", .wood, 0.91, 0.78, 0.55),
        .init("poplar", "Poplar Plywood", .wood, 0.93, 0.86, 0.68),
        .init("beech", "Beech", .wood, 0.86, 0.66, 0.46),
        .init("cherry", "Cherry", .wood, 0.72, 0.43, 0.27),
        .init("walnut", "Walnut", .wood, 0.46, 0.31, 0.21),
        .init("mdf", "MDF", .wood, 0.66, 0.50, 0.34),
        .init("white", "White", .acrylic, 0.95, 0.95, 0.94),
        .init("black", "Black", .acrylic, 0.08, 0.08, 0.09),
        .init("red", "Red", .acrylic, 0.80, 0.10, 0.12),
        .init("orange", "Orange", .acrylic, 0.95, 0.45, 0.08),
        .init("yellow", "Yellow", .acrylic, 0.98, 0.82, 0.10),
        .init("green", "Green", .acrylic, 0.10, 0.55, 0.25),
        .init("blue", "Blue", .acrylic, 0.10, 0.30, 0.75),
        .init("clear", "Clear", .clearAcrylic, 0.92, 0.96, 0.98),
        .init("smoke", "Smoke", .clearAcrylic, 0.35, 0.35, 0.38),
        .init("clear-red", "Transparent Red", .clearAcrylic, 0.90, 0.12, 0.15),
        .init("clear-orange", "Transparent Orange", .clearAcrylic, 1.00, 0.50, 0.10),
        .init("clear-yellow", "Transparent Yellow", .clearAcrylic, 1.00, 0.85, 0.15),
        .init("clear-green", "Transparent Green", .clearAcrylic, 0.15, 0.70, 0.35),
        .init("clear-blue", "Transparent Blue", .clearAcrylic, 0.15, 0.40, 0.90),
    ]

    static func named(_ id: String) -> SheetMaterial { all.first { $0.id == id } ?? standard }
    /// The gallery and every newly opened box show MDF.
    static let standard = all.first { $0.id == "mdf" }!

    private static let materials = Dictionary(uniqueKeysWithValues: all.map { ($0.id, $0.makeMaterial()) })
    var scn: SCNMaterial { Self.materials[id]! }

    /// Wood edges are laser-browned; acrylic edges keep the colour, and clear acrylic's glow a little.
    private func makeMaterial() -> SCNMaterial {
        switch kind {
        case .wood: Self.surface(color, roughness: 0.8, edge: "float3(0.46, 0.37, 0.31)")
        case .acrylic: Self.surface(color, roughness: 0.25, edge: "float3(0.85)")
        case .clearAcrylic: Self.surface(color, roughness: 0.05, edge: "float3(1.25)")
        }
    }

    /// The extrusion's side faces (normal ⟂ z) are the cut edges: their colour is multiplied by `edge`.
    static func surface(_ color: NSColor, roughness: Double, edge: String) -> SCNMaterial {
        let m = SCNMaterial()
        m.diffuse.contents = color
        m.lightingModel = .physicallyBased
        m.roughness.contents = roughness
        m.metalness.contents = 0.0
        m.isDoubleSided = true
        m.shaderModifiers = [
            .geometry: "_geometry.texcoords[0] = float2(abs(_geometry.normal.z), 0.0);",
            .surface: "_surface.diffuse.rgb *= mix(\(edge), float3(1.0), smoothstep(0.3, 0.7, _surface.diffuseTexcoord.x));",
        ]
        return m
    }

    /// A round colour chip for the menu.
    var swatch: NSImage {
        NSImage(size: NSSize(width: 14, height: 14), flipped: false) { rect in
            let dot = NSBezierPath(ovalIn: rect.insetBy(dx: 1, dy: 1))
            color.withAlphaComponent(kind == .clearAcrylic ? 0.55 : 1).setFill()
            dot.fill()
            NSColor.separatorColor.setStroke()
            dot.stroke()
            return true
        }
    }
}
