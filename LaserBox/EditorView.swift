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
    @AppStorage("showsLids") private var showsLids = true
    @State private var exploded = false

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
                                 material: SheetMaterial.named(materialID), decorations: showsDecorations, lids: showsLids,
                                 exploded: exploded)
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
                if model.assembly?.pieces.contains(where: { $0.decoration != nil }) == true {
                    Toggle(isOn: $showsDecorations) {
                        Label("Decorations", systemImage: "sparkles")
                    }
                    .toggleStyle(.button)
                    .help("Show or hide the decorations: what goes in the box and removable panels")
                }
                if model.assembly?.pieces.contains(where: { $0.lid == true }) == true {
                    Toggle(isOn: $showsLids) {
                        Label("Lids", systemImage: "archivebox")
                    }
                    .toggleStyle(.button)
                    .help("Show or hide the lids")
                }
                if (model.assembly.map { Set($0.pieces.compactMap(\.part)).count } ?? 0) > 1 {
                    Toggle(isOn: $exploded) {
                        Label("Exploded View", systemImage: "arrow.up.left.and.arrow.down.right")
                    }
                    .toggleStyle(.button)
                    .help("Pull the parts apart to show how they go together")
                }
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
                            rows(group.args)
                        }
                    } else {
                        let plain = group.args.filter { $0.kind != "panels" }
                        if !plain.isEmpty { Section(group.title) { rows(plain) } }
                        ForEach(group.args.filter { $0.kind == "panels" }) { arg in
                            FrontPanelSections(text: Binding { model.value(arg) } set: { model.set($0, for: arg) })
                        }
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

    private func rows(_ args: [Arg]) -> some View {
        ForEach(args) { arg in
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

/// Title, summary and the long description from boxes.py: text only, no pictures.
struct BoxInfo: View {
    let generator: GeneratorInfo
    let html: String

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text(generator.title).font(.title3.bold())
                Text(generator.doc).foregroundStyle(.secondary)
                if !html.isEmpty {
                    HTMLView(html: html)
                        .frame(height: 220)
                }
            }
            .padding()
        }
        .frame(width: 440)
        .frame(maxHeight: 700)
    }
}

/// Renders the description HTML.
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
            a { color: -apple-system-control-accent; }
            </style></head><body>\(html)</body></html>
            """, baseURL: nil)
    }
}

/// Shows the SVG as a blueprint: white lines and lettering on blue paper with a 10 mm grid. Only the look
/// on screen: the exported files keep boxes.py's colours. Updates replace the drawing in place, so zoom
/// (pinch) and scroll survive.
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
            svg { flex: 1; width: 100%; height: 100%; box-shadow: 0 1px 6px rgba(0,0,0,.35);
                  background: radial-gradient(ellipse at 30% 20%, #2662ad, #1a4b8c 60%, #143d75); }
            svg > g path { stroke: #fff; stroke-width: 1.1px; vector-effect: non-scaling-stroke; }
            svg > g path[stroke="rgb(0,255,0)"], svg > g path[stroke="rgb(0,255,255)"] { stroke: rgba(255,255,255,.7); }
            svg > g path[stroke="rgb(255,0,0)"] { stroke: rgba(255,255,255,.45); stroke-width: .8px; }
            svg text { fill: #fff !important; font-family: "DIN Alternate", "Avenir Next Condensed", sans-serif !important;
                       letter-spacing: .04em; }
            svg text[style*="255,0,0"] { fill: rgba(255,255,255,.6) !important; }
            </style><script>
            const grid = `<defs>
              <pattern id="bp-minor" width="10" height="10" patternUnits="userSpaceOnUse">
                <path d="M10 0H0V10" fill="none" stroke="rgba(255,255,255,.10)" stroke-width=".25"/></pattern>
              <pattern id="bp-major" width="50" height="50" patternUnits="userSpaceOnUse">
                <rect width="50" height="50" fill="url(#bp-minor)"/>
                <path d="M50 0H0V50" fill="none" stroke="rgba(255,255,255,.22)" stroke-width=".4"/></pattern>
              </defs><rect x="-10000" y="-10000" width="20000" height="20000" fill="url(#bp-major)"/>`;
            function show(svg) {
              const paper = document.getElementById('paper');
              paper.innerHTML = svg;
              paper.querySelector('svg')?.insertAdjacentHTML('afterbegin', grid);
            }
            </script></head><body><div id="paper"></div></body></html>
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
            view.callAsyncJavaScript("show(svg)", arguments: ["svg": svg], in: nil, in: .page)
        }

        func webView(_ view: WKWebView, didFinish navigation: WKNavigation!) {
            loaded = true
            if let pending { show(pending, in: view) }
        }
    }
}

/// The assembled box: every piece extruded and placed in the chosen material, plus its lids and decorations.
/// `interactive` gives the full orbit/zoom camera and lets hinged and sliding parts be dragged; otherwise
/// `yaw`/`pitch` turn the box.
struct AssemblyView: NSViewRepresentable {
    let assembly: Assembly
    let key: String          // changes when the geometry changes
    var material = SheetMaterial.standard
    var decorations = true
    var lids = true
    var exploded = false
    var interactive = true
    var yaw: CGFloat = 0
    var pitch: CGFloat = 0

    func makeNSView(context: Context) -> SCNView {
        let view = JointView()
        view.stage = interactive ? context.coordinator : nil
        view.allowsCameraControl = interactive
        view.autoenablesDefaultLighting = false
        view.antialiasingMode = .multisampling4X
        view.backgroundColor = .clear
        view.scene = context.coordinator.scene
        view.pointOfView = context.coordinator.camera
        return view
    }

    func updateNSView(_ view: SCNView, context: Context) {
        let stage = context.coordinator
        // The editor builds every piece, framed on the whole box, and only hides lids and decorations,
        // so toggling them leaves the camera alone; the gallery leaves them out, framing what it shows.
        let key = interactive ? "\(key)|\(material.id)" : "\(key)|\(material.id)|\(decorations)|\(lids)"
        if stage.key != key {
            stage.key = key
            let size = stage.build(assembly, material: material, decorations: decorations, lids: lids, all: interactive)
            if abs(size - stage.size) > 0.5 || !interactive {
                stage.size = size
                stage.frame(size: size, interactive: interactive)
                view.pointOfView = stage.camera
            }
        }
        stage.show(decorations: decorations, lids: lids)
        if stage.exploded != exploded { stage.explode(exploded, animated: true) }
        stage.spin.eulerAngles = SCNVector3(pitch, yaw, 0)
    }

    func makeCoordinator() -> AssemblyStage { AssemblyStage() }
}

/// The editor's 3D view: dragging a hinged or sliding part moves it through its range, anywhere else
/// turns the camera.
final class JointView: SCNView {
    weak var stage: AssemblyStage?
    private var grip: (joint: Int, at: SCNVector3, mouse: CGPoint)?  // the point taken, in the joint's frame

    override func mouseDown(with event: NSEvent) {
        let p = convert(event.locationInWindow, from: nil)
        if let stage, !stage.exploded, let hit = hitTest(p).first, let j = stage.joint(of: hit.node) {
            grip = (j, stage.joints[j].node.convertPosition(hit.localCoordinates, from: hit.node), p)
        } else {
            super.mouseDown(with: event)
        }
    }

    override func mouseDragged(with event: NSEvent) {
        guard let grip, let stage else { return super.mouseDragged(with: event) }
        let p = convert(event.locationInWindow, from: nil)
        stage.drag(grip.joint, grip: grip.at, by: CGPoint(x: p.x - grip.mouse.x, y: p.y - grip.mouse.y), in: self)
        self.grip?.mouse = p
    }

    override func mouseUp(with event: NSEvent) {
        if grip == nil { super.mouseUp(with: event) }
        grip = nil
    }
}

/// A gallery card: a scene GalleryScenes built, only attached and turned here.
struct StageView: NSViewRepresentable {
    let stage: AssemblyStage
    var yaw: CGFloat = 0
    var pitch: CGFloat = 0

    func makeNSView(context: Context) -> SCNView {
        let view = SCNView()
        view.autoenablesDefaultLighting = false
        view.antialiasingMode = .multisampling4X
        view.backgroundColor = .clear
        view.scene = stage.scene
        view.pointOfView = stage.camera
        return view
    }

    func updateNSView(_ view: SCNView, context: Context) {
        if view.scene !== stage.scene {
            view.scene = stage.scene
            view.pointOfView = stage.camera
        }
        stage.spin.eulerAngles = SCNVector3(pitch, stage.turn + yaw, 0)
    }
}

/// An assembled box's scene: lights, camera and the pieces under `spin`. It has nothing to do with
/// the interface, so the gallery builds and renders its pictures off the main thread.
final class AssemblyStage {
    var key = ""
    var optional: [(node: SCNNode, piece: Piece)] = []  // lids and decorations, shown or hidden
    var moving: [(node: SCNNode, home: SCNVector3, away: SCNVector3?, opacity: CGFloat)] = []  // see explode
    var joints: [(node: SCNNode, joint: Joint, value: Double)] = []  // the hinged and sliding parts' frames
    var exploded = false
    var zoom: CGFloat = 1   // how much the exploded view needs the camera to zoom out
    var size: CGFloat = 0
    var turn: CGFloat = 0   // the gallery's yaw for this box
    let scene = SCNScene()
    let spin = SCNNode()
    let camera = SCNNode()
    let sun = SCNNode()

    init() {
        scene.background.contents = NSColor.clear
        scene.rootNode.addChildNode(spin)

        let cam = SCNCamera()
        cam.usesOrthographicProjection = true
        cam.zNear = 1; cam.zFar = 10000
        // Ambient occlusion darkens the joints and the inside corners.
        cam.screenSpaceAmbientOcclusionIntensity = 2.2
        cam.screenSpaceAmbientOcclusionBias = 0.3
        cam.screenSpaceAmbientOcclusionDepthThreshold = 2
        cam.screenSpaceAmbientOcclusionNormalThreshold = 0.1
        camera.camera = cam
        scene.rootNode.addChildNode(camera)

        let light = SCNLight()
        light.type = .directional; light.intensity = 850
        light.castsShadow = true; light.shadowMode = .deferred; light.shadowSampleCount = 32
        light.shadowMapSize = CGSize(width: 2048, height: 2048)
        light.shadowRadius = 5; light.shadowColor = NSColor(white: 0, alpha: 0.55)
        light.automaticallyAdjustsShadowProjection = false
        sun.light = light
        scene.rootNode.addChildNode(sun)

        let fill = SCNNode()
        fill.light = SCNLight(); fill.light!.type = .directional; fill.light!.intensity = 250
        fill.position = SCNVector3(-1, 0.5, -1); fill.look(at: SCNVector3Zero)
        scene.rootNode.addChildNode(fill)

        let ambient = SCNNode()
        ambient.light = SCNLight(); ambient.light!.type = .ambient; ambient.light!.intensity = 330
        scene.rootNode.addChildNode(ambient)
    }

    /// Puts the assembly's pieces under `spin`, centred: all of them, or only those shown. Returns the
    /// box's diagonal, which frames it from any angle.
    func build(_ assembly: Assembly, material: SheetMaterial, decorations: Bool, lids: Bool, all: Bool) -> CGFloat {
        spin.childNodes.forEach { $0.removeFromParentNode() }
        optional = []
        let box = SCNNode()
        joints = (assembly.joints ?? []).map { joint in
            let node = SCNNode()
            box.addChildNode(node)
            return (node, joint, joint.start ?? 0)
        }
        joints.indices.forEach(pose)
        var built: [(SCNNode, Piece)] = []
        for piece in assembly.pieces where all || Self.shown(piece, decorations: decorations, lids: lids) {
            let node = Self.node(for: piece, material: material)
            (piece.joint.map { joints[$0].node } ?? box).addChildNode(node)
            built.append((node, piece))
            if piece.lid == true || piece.decoration != nil { optional.append((node, piece)) }
        }
        let (minV, maxV) = box.boundingBox
        let dx = maxV.x - minV.x, dy = maxV.y - minV.y, dz = maxV.z - minV.z
        let size = sqrt(dx * dx + dy * dy + dz * dz)
        // only the editor explodes the box: the gallery's cards skip the work
        let (away, spread) = all ? Self.explosion(built.map(\.1), centre: SCNVector3((minV.x + maxV.x) / 2, (minV.y + maxV.y) / 2,
                                                                                      (minV.z + maxV.z) / 2), size: size) : ([:], size)
        zoom = max(1, spread / size)
        moving = built.map { node, piece in (node, node.position, piece.part.flatMap { away[$0] }, node.opacity) }
        place()
        box.position = SCNVector3(-(minV.x + maxV.x) / 2, -(minV.y + maxV.y) / 2, -(minV.z + maxV.z) / 2)
        let tilt = SCNNode()           // boxes.py is z-up, SceneKit y-up
        tilt.eulerAngles.x = -.pi / 2
        tilt.addChildNode(box)
        spin.addChildNode(tilt)
        return size
    }

    /// How far the exploded view pulls the parts out: a share of their distance from the box's centre,
    /// plus a share of the box's size so that parts near the middle come off too.
    static let spread: CGFloat = 0.6
    static let gap: CGFloat = 0.08

    /// Each part's way out of the box in the exploded view. A flat part goes along its normal, by its
    /// distance from the centre that way (a divider through the middle stays, the walls round it go
    /// out, the floor down, the lid up); a bent one (its pieces facing different ways) straight away
    /// from the centre. Parts that would still go through each other (dividers slotted into each
    /// other, a slope through a divider) are then settled one by one, those going farthest first: a
    /// part hitting one already settled is lifted above it (lowered below it, if it was going down),
    /// so the inner ones end up stacked in layers. Decorations not cut from the sheet have no part:
    /// they fade out instead.
    /// The whole is then moved back onto the box's centre; returns the moves and the exploded parts'
    /// diagonal.
    static func explosion(_ pieces: [Piece], centre: SCNVector3, size: CGFloat) -> (away: [Int: SCNVector3], size: CGFloat) {
        typealias V3 = SIMD3<Double>
        /// A piece as a box: its centre, its axes (u, v, normal) and half its extent along each.
        struct Slab { let centre: V3; let axes: [V3]; let half: V3 }
        let size = Double(size), c0 = V3(Double(centre.x), Double(centre.y), Double(centre.z))
        var parts: [Int: (normal: V3, flat: Bool, slabs: [Slab])] = [:]
        for piece in pieces {
            guard let part = piece.part, let ring = piece.rings.first, !ring.isEmpty else { continue }
            let u = V3(piece.u[0], piece.u[1], piece.u[2]), v = V3(piece.v[0], piece.v[1], piece.v[2])
            let n = simd_cross(u, v) * Double(piece.side)
            let us = ring.map { $0[0] }, vs = ring.map { $0[1] }
            let (u0, u1, v0, v1) = (us.min()!, us.max()!, vs.min()!, vs.max()!)
            let o = V3(piece.origin[0], piece.origin[1], piece.origin[2])
            let slab = Slab(centre: o + (u0 + u1) / 2 * u + (v0 + v1) / 2 * v + piece.t / 2 * n,
                            axes: [u, v, n], half: V3((u1 - u0) / 2, (v1 - v0) / 2, piece.t / 2))
            if var p = parts[part] {
                p.flat = p.flat && abs(simd_dot(p.normal, n)) > 0.999
                p.slabs.append(slab)
                parts[part] = p
            } else {
                parts[part] = (n, true, [slab])
            }
        }
        var away = parts.mapValues { p -> V3 in
            let d = p.slabs.reduce(V3.zero) { $0 + $1.centre } / Double(p.slabs.count) - c0
            let w = p.flat ? p.normal : d
            let along = p.flat ? simd_dot(p.normal, d) : simd_length(d)   // the distance out, along w
            if abs(along) < 0.01 * size { return .zero }
            return w * ((abs(along) * Double(spread) + Double(gap) * size) / abs(along) * (p.flat ? along : 1))
        }

        // Separating axis test between two slabs moved by da and db; touching faces don't count.
        func hit(_ a: Slab, _ da: V3, _ b: Slab, _ db: V3) -> Bool {
            let t = b.centre + db - a.centre - da
            var axes = a.axes + b.axes
            for x in a.axes { for y in b.axes { axes.append(simd_cross(x, y)) } }
            for axis in axes {
                let l = simd_length(axis)
                if l < 1e-6 { continue }
                let L = axis / l
                let ra = (0..<3).reduce(0.0) { $0 + a.half[$1] * abs(simd_dot(a.axes[$1], L)) }
                let rb = (0..<3).reduce(0.0) { $0 + b.half[$1] * abs(simd_dot(b.axes[$1], L)) }
                if abs(simd_dot(t, L)) > ra + rb - 0.3 { return false }
            }
            return true
        }
        func bounds(_ k: Int) -> (lo: V3, hi: V3) {
            var lo = V3(repeating: .infinity), hi = V3(repeating: -.infinity)
            for s in parts[k]!.slabs {
                let r = (0..<3).reduce(V3.zero) { $0 + s.half[$1] * abs(s.axes[$1]) }
                lo = simd_min(lo, s.centre + away[k]! - r); hi = simd_max(hi, s.centre + away[k]! + r)
            }
            return (lo, hi)
        }
        var settled: [(part: Int, lo: V3, hi: V3)] = []   // they don't move any more
        for k in parts.keys.sorted(by: { (simd_length(away[$0]!), $1) > (simd_length(away[$1]!), $0) }) {
            let up = away[k]!.z >= -1e-6
            for _ in 0..<60 {
                let box = bounds(k)
                let hits = settled.filter { j in
                    guard all(box.lo .< j.hi) && all(j.lo .< box.hi) else { return false }
                    return parts[k]!.slabs.contains { a in parts[j.part]!.slabs.contains { b in hit(a, away[k]!, b, away[j.part]!) } }
                }
                if hits.isEmpty { break }
                away[k]!.z += up ? hits.map(\.hi.z).max()! - box.lo.z + 0.04 * size : hits.map(\.lo.z).min()! - box.hi.z - 0.04 * size
            }
            let box = bounds(k)
            settled.append((k, box.lo, box.hi))
        }
        var lo = V3(repeating: .infinity), hi = V3(repeating: -.infinity)
        for b in settled { lo = simd_min(lo, b.lo); hi = simd_max(hi, b.hi) }
        guard !parts.isEmpty else { return ([:], CGFloat(size)) }
        let shift = (lo + hi) / 2 - c0
        return (away.mapValues { SCNVector3($0.x - shift.x, $0.y - shift.y, $0.z - shift.z) }, CGFloat(simd_length(hi - lo)))
    }

    /// Pulls the parts apart (or puts them back), animated: decorations fade, the camera zooms out, the
    /// hinged and sliding parts close first.
    func explode(_ on: Bool, animated: Bool) {
        exploded = on
        SCNTransaction.begin()
        SCNTransaction.animationDuration = animated ? 0.8 : 0
        SCNTransaction.animationTimingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
        place()
        joints.indices.forEach(pose)
        if let cam = camera.camera {
            cam.orthographicScale *= Double(on ? zoom : 1 / zoom)
            sun.light?.orthographicScale *= on ? zoom : 1 / zoom
        }
        SCNTransaction.commit()
    }

    private func place() {
        for (node, home, away, opacity) in moving {
            if let away {
                node.position = exploded ? SCNVector3(home.x + away.x, home.y + away.y, home.z + away.z) : home
            } else {
                node.opacity = exploded ? 0 : opacity
            }
        }
    }

    /// Puts a joint's parts where its value says; closed in the exploded view, which moves them from there.
    private func pose(_ i: Int) {
        let (node, joint, value) = joints[i]
        let v = Float(exploded ? 0 : value), axis = SIMD3<Float>(joint.axis.map(Float.init))
        if joint.kind == "hinge", let at = joint.at.map({ SIMD3<Float>($0.map(Float.init)) }) {
            let turn = simd_quatf(angle: v * .pi / 180, axis: axis)
            node.simdOrientation = turn
            node.simdPosition = at - turn.act(at)
        } else {
            node.simdPosition = axis * v
        }
    }

    /// The joint a piece's node moves with.
    func joint(of node: SCNNode) -> Int? { joints.firstIndex { $0.node === node.parent } }

    /// Moves joint i so that `grip` (a point of its parts, in its frame) follows the mouse, moved by `delta`
    /// in the view: by the share of the move along the way the point goes on screen, kept within range.
    func drag(_ i: Int, grip: SCNVector3, by delta: CGPoint, in view: SCNView) {
        let (node, joint, value) = joints[i]
        guard !exploded, let frame = node.parent else { return }
        let p = node.simdConvertPosition(SIMD3<Float>(grip), to: nil)
        let axis = frame.simdConvertVector(SIMD3<Float>(joint.axis.map(Float.init)), to: nil)
        var step = axis   // how far p goes for one unit of value: a mm, or a degree
        if joint.kind == "hinge", let at = joint.at {
            step = simd_cross(axis, p - frame.simdConvertPosition(SIMD3<Float>(at.map(Float.init)), to: nil)) * .pi / 180
        }
        let a = view.projectPoint(SCNVector3(p)), b = view.projectPoint(SCNVector3(p + step))
        let sx = b.x - a.x, sy = b.y - a.y, l2 = sx * sx + sy * sy
        guard l2 > 1e-6 else { return }
        joints[i].value = min(max(value + Double((delta.x * sx + delta.y * sy) / l2), joint.range[0]), joint.range[1])
        pose(i)
    }

    func show(decorations: Bool, lids: Bool) {
        for (node, piece) in optional { node.isHidden = !Self.shown(piece, decorations: decorations, lids: lids) }
    }

    static func shown(_ piece: Piece, decorations: Bool, lids: Bool) -> Bool {
        piece.lid == true ? lids : piece.decoration == nil || decorations
    }

    func frame(size: CGFloat, interactive: Bool) {
        let cam = camera.camera!
        cam.orthographicScale = Double(size) * (interactive ? 0.6 : 0.54)
        camera.position = SCNVector3(size * 2, size * 1.5, size * 2)
        camera.look(at: SCNVector3Zero)
        cam.zFar = Double(size) * 20
        cam.screenSpaceAmbientOcclusionRadius = Double(size) * 0.05
        if exploded { cam.orthographicScale *= Double(zoom) }
        let light = sun.light!
        light.orthographicScale = Double(size) * 1.2 * (exploded ? zoom : 1)
        light.zNear = 1; light.zFar = Double(size) * 8   // the shadow map must reach the whole box
        sun.position = SCNVector3(size * 0.9, size * 2.2, size * 1.4)
        sun.look(at: SCNVector3Zero)
    }

    /// A gallery card's scene: MDF, lids left out unless the box asks for them, framed for the card,
    /// turned by the box's `turn`.
    static func gallery(_ assembly: Assembly) -> AssemblyStage {
        let stage = AssemblyStage()
        let size = stage.build(assembly, material: .standard, decorations: true, lids: assembly.galleryLids ?? false, all: false)
        stage.frame(size: size, interactive: false)
        stage.turn = (assembly.turn ?? 0) * .pi / 180
        stage.spin.eulerAngles = SCNVector3(0, stage.turn, 0)
        return stage
    }

    /// Decoration kinds (assembly.py) and their look.
    private static let decorationMaterials = [
        "paper": SheetMaterial.surface(NSColor(red: 0.99, green: 0.95, blue: 0.62, alpha: 1), roughness: 0.95, edge: "float3(0.85)"),
        "dice": SheetMaterial.surface(NSColor(red: 0.96, green: 0.94, blue: 0.88, alpha: 1), roughness: 0.35, edge: "float3(0.92)"),
        "pip": SheetMaterial.surface(NSColor(red: 0.08, green: 0.08, blue: 0.10, alpha: 1), roughness: 0.5, edge: "float3(1.0)"),
        "cards": SheetMaterial.surface(NSColor(red: 0.97, green: 0.96, blue: 0.93, alpha: 1), roughness: 0.6, edge: "float3(0.88)"),
        "cardback": SheetMaterial.surface(NSColor(red: 0.70, green: 0.10, blue: 0.13, alpha: 1), roughness: 0.45, edge: "float3(1.0)"),
        "cardback-blue": SheetMaterial.surface(NSColor(red: 0.12, green: 0.20, blue: 0.62, alpha: 1), roughness: 0.45, edge: "float3(1.0)"),
        "keycap": SheetMaterial.surface(NSColor(red: 0.95, green: 0.95, blue: 0.93, alpha: 1), roughness: 0.4, edge: "float3(0.9)"),
        "pen": SheetMaterial.surface(NSColor(red: 0.86, green: 0.89, blue: 0.92, alpha: 1), roughness: 0.15, edge: "float3(0.95)"),
        "pen-cap": SheetMaterial.surface(NSColor(red: 0.10, green: 0.25, blue: 0.75, alpha: 1), roughness: 0.35, edge: "float3(0.9)"),
        "pen-tip": SheetMaterial.surface(NSColor(red: 0.80, green: 0.80, blue: 0.82, alpha: 1), roughness: 0.2, edge: "float3(0.9)"),
        "bottle": SheetMaterial.surface(NSColor(red: 0.07, green: 0.20, blue: 0.10, alpha: 1), roughness: 0.1, edge: "float3(1.0)"),
        "bottle-amber": SheetMaterial.surface(NSColor(red: 0.30, green: 0.14, blue: 0.04, alpha: 1), roughness: 0.1, edge: "float3(1.0)"),
        "capsule-red": SheetMaterial.surface(NSColor(red: 0.50, green: 0.06, blue: 0.10, alpha: 1), roughness: 0.3, edge: "float3(0.9)"),
        "capsule-gold": SheetMaterial.surface(NSColor(red: 0.78, green: 0.62, blue: 0.30, alpha: 1), roughness: 0.3, edge: "float3(0.9)"),
        "label": SheetMaterial.surface(NSColor(red: 0.95, green: 0.92, blue: 0.84, alpha: 1), roughness: 0.8, edge: "float3(0.95)"),
        "tin": SheetMaterial.surface(NSColor(red: 0.12, green: 0.12, blue: 0.13, alpha: 1), roughness: 0.4, edge: "float3(1.0)"),
        "lid-wood": SheetMaterial.surface(NSColor(red: 0.62, green: 0.44, blue: 0.26, alpha: 1), roughness: 0.7, edge: "float3(0.85)"),
        "spice-red": SheetMaterial.surface(NSColor(red: 0.70, green: 0.20, blue: 0.08, alpha: 1), roughness: 0.9, edge: "float3(1.0)"),
        "spice-yellow": SheetMaterial.surface(NSColor(red: 0.85, green: 0.62, blue: 0.10, alpha: 1), roughness: 0.9, edge: "float3(1.0)"),
        "spice-green": SheetMaterial.surface(NSColor(red: 0.38, green: 0.45, blue: 0.20, alpha: 1), roughness: 0.9, edge: "float3(1.0)"),
        "spice-brown": SheetMaterial.surface(NSColor(red: 0.42, green: 0.26, blue: 0.14, alpha: 1), roughness: 0.9, edge: "float3(1.0)"),
        "vinyl": SheetMaterial.surface(NSColor(red: 0.05, green: 0.05, blue: 0.06, alpha: 1), roughness: 0.25, edge: "float3(1.0)"),
        "vinyl-groove": SheetMaterial.surface(NSColor(red: 0.16, green: 0.16, blue: 0.18, alpha: 1), roughness: 0.15, edge: "float3(1.0)"),
        "vinyl-red": SheetMaterial.surface(NSColor(red: 0.75, green: 0.15, blue: 0.12, alpha: 1), roughness: 0.7, edge: "float3(0.95)"),
        "vinyl-blue": SheetMaterial.surface(NSColor(red: 0.15, green: 0.30, blue: 0.65, alpha: 1), roughness: 0.7, edge: "float3(0.95)"),
        "vinyl-yellow": SheetMaterial.surface(NSColor(red: 0.92, green: 0.75, blue: 0.20, alpha: 1), roughness: 0.7, edge: "float3(0.95)"),
        "paint-red": SheetMaterial.surface(NSColor(red: 0.75, green: 0.10, blue: 0.08, alpha: 1), roughness: 0.5, edge: "float3(1.0)"),
        "paint-blue": SheetMaterial.surface(NSColor(red: 0.10, green: 0.25, blue: 0.65, alpha: 1), roughness: 0.5, edge: "float3(1.0)"),
        "paint-yellow": SheetMaterial.surface(NSColor(red: 0.92, green: 0.75, blue: 0.10, alpha: 1), roughness: 0.5, edge: "float3(1.0)"),
        "paint-green": SheetMaterial.surface(NSColor(red: 0.15, green: 0.45, blue: 0.20, alpha: 1), roughness: 0.5, edge: "float3(1.0)"),
        "paint-white": SheetMaterial.surface(NSColor(red: 0.93, green: 0.93, blue: 0.90, alpha: 1), roughness: 0.5, edge: "float3(1.0)"),
        "paint-black": SheetMaterial.surface(NSColor(red: 0.10, green: 0.10, blue: 0.11, alpha: 1), roughness: 0.5, edge: "float3(1.0)"),
        "pegboard": SheetMaterial.surface(NSColor(red: 0.94, green: 0.94, blue: 0.92, alpha: 1), roughness: 0.8, edge: "float3(0.9)"),
        "rail": SheetMaterial.surface(NSColor(red: 0.78, green: 0.80, blue: 0.82, alpha: 1), roughness: 0.3, edge: "float3(0.95)"),
        "towel": SheetMaterial.surface(NSColor(red: 0.97, green: 0.97, blue: 0.95, alpha: 1), roughness: 0.95, edge: "float3(0.9)"),
        "cardboard": SheetMaterial.surface(NSColor(red: 0.62, green: 0.47, blue: 0.32, alpha: 1), roughness: 0.9, edge: "float3(0.9)"),
        "dowel": SheetMaterial.surface(NSColor(red: 0.80, green: 0.64, blue: 0.42, alpha: 1), roughness: 0.7, edge: "float3(0.9)"),
        "iron": SheetMaterial.surface(NSColor(red: 0.12, green: 0.15, blue: 0.22, alpha: 1), roughness: 0.45, edge: "float3(0.9)"),
        "steel": SheetMaterial.surface(NSColor(red: 0.72, green: 0.74, blue: 0.77, alpha: 1), roughness: 0.25, edge: "float3(0.95)"),
        "wood-handle": SheetMaterial.surface(NSColor(red: 0.45, green: 0.22, blue: 0.12, alpha: 1), roughness: 0.55, edge: "float3(0.9)"),
        "caliper-body": SheetMaterial.surface(NSColor(red: 0.16, green: 0.16, blue: 0.17, alpha: 1), roughness: 0.5, edge: "float3(0.95)"),
        "lcd": SheetMaterial.surface(NSColor(red: 0.55, green: 0.60, blue: 0.52, alpha: 1), roughness: 0.3, edge: "float3(1.0)"),
        "brass": SheetMaterial.surface(NSColor(red: 0.80, green: 0.65, blue: 0.30, alpha: 1), roughness: 0.3, edge: "float3(0.95)"),
        "grip-red": SheetMaterial.surface(NSColor(red: 0.75, green: 0.12, blue: 0.10, alpha: 1), roughness: 0.6, edge: "float3(0.95)"),
        "grip-yellow": SheetMaterial.surface(NSColor(red: 0.93, green: 0.75, blue: 0.12, alpha: 1), roughness: 0.6, edge: "float3(0.95)"),
        "grip-black": SheetMaterial.surface(NSColor(red: 0.12, green: 0.12, blue: 0.13, alpha: 1), roughness: 0.6, edge: "float3(0.95)"),
        "hss": SheetMaterial.surface(NSColor(red: 0.18, green: 0.18, blue: 0.20, alpha: 1), roughness: 0.35, edge: "float3(0.95)"),
        "hss-gold": SheetMaterial.surface(NSColor(red: 0.80, green: 0.62, blue: 0.25, alpha: 1), roughness: 0.3, edge: "float3(0.95)"),
        "pcb": SheetMaterial.surface(NSColor(red: 0.05, green: 0.38, blue: 0.17, alpha: 1), roughness: 0.5, edge: "float3(0.95)"),
    ]

    /// SCNShape extrudes a flat path along z, centred; the path's even-odd rule turns inner rings into holes.
    static func node(for piece: Piece, material: SheetMaterial) -> SCNNode {
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
        if let kind = piece.decoration, let look = decorationMaterials[kind] {
            shape.materials = [look]
        } else {  // the box's own parts, lids, and decorations cut from the sheet (a panel)
            let material = piece.clear == true ? SheetMaterial.named("clear") : material
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
