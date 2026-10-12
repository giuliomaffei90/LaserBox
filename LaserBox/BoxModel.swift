import AppKit
import CryptoKit
import Observation
import SceneKit

@Observable @MainActor
final class BoxModel {
    var groups: [GeneratorGroup] = []
    /// The generator open in the editor.
    var selection: String? {
        didSet { if selection != oldValue { spec = nil; svg = nil; assembly = nil; assemblyError = nil; error = nil; Task { await loadSpec() } } }
    }
    var spec: GeneratorSpec?
    var svg: String?
    var assembly: Assembly?
    /// Identifies the geometry in `assembly` (generator + parameters) so views rebuild only when it changes.
    var assemblyKey = ""
    /// Why the 3D view is unavailable for this box (no recipe yet, or a failure).
    var assemblyError: String?
    var showsAssembly = false {
        didSet { if showsAssembly, assembly == nil { scheduleRender(delay: .zero) } }
    }
    var error: String?
    var isRendering = false
    var startupError: String?
    /// The gallery cards' 3D scenes, boxes with default parameters (see GalleryScenes).
    var galleryStages: [String: AssemblyStage] = [:]
    /// The scenes being prepared at launch, done of all; nil once the gallery can show.
    var preparing: (done: Int, of: Int)?

    /// Values the user changed, per generator, so switching box type and back keeps them.
    private var overrides: [String: [String: String]] = [:]
    private var bridge: Bridge?
    private var renderTask: Task<Void, Never>?

    func start() async {
        do {
            let bridge = try Bridge()
            self.bridge = bridge
            groups = try await bridge.list()
        } catch {
            startupError = error.localizedDescription
            return
        }
        await prepareGallery()
    }

    /// Every 3D card's scene, ready before the gallery shows and kept for the whole session. A few at
    /// a time, so Python assembles the next boxes while SceneKit builds one.
    private func prepareGallery() async {
        let names = Set(groups.flatMap(\.generators).filter(\.assembled).map(\.name)).sorted()
        preparing = (0, names.count)
        await withTaskGroup(of: Void.self) { group in
            var next = names.makeIterator()
            for _ in 0..<3 {
                if let name = next.next() { group.addTask { await self.loadGalleryStage(name) } }
            }
            for await _ in group {
                preparing?.done += 1
                if let name = next.next() { group.addTask { await self.loadGalleryStage(name) } }
            }
        }
        preparing = nil
    }

    func value(_ arg: Arg) -> String {
        overrides[spec?.name ?? ""]?[arg.name] ?? arg.default
    }

    func set(_ value: String, for arg: Arg) {
        guard let name = spec?.name else { return }
        overrides[name, default: [:]][arg.name] = value == arg.default ? nil : value
        scheduleRender()
    }

    var hasOverrides: Bool {
        !(overrides[spec?.name ?? ""]?.isEmpty ?? true)
    }

    func resetToDefaults() {
        guard let name = spec?.name else { return }
        overrides[name] = nil
        scheduleRender(delay: .zero)
    }

    /// A card's scene: its box from disk, or from Python (and kept on disk), built off the main thread.
    func loadGalleryStage(_ name: String) async {
        guard galleryStages[name] == nil else { return }
        var assembly = await GalleryScenes.shared.cached(name)
        if assembly == nil, let bridge, let fresh = try? await bridge.assemble(name, args: [:]) {
            assembly = fresh
            await GalleryScenes.shared.keep(fresh, as: name)
        }
        guard let assembly else { return }
        galleryStages[name] = await GalleryScenes.shared.stage(for: assembly)
    }

    /// The cut file in the given format ("svg" or "dxf") for the current settings.
    func export(format: String) async throws -> Data {
        guard let bridge, let name = spec?.name else { throw BridgeError(errorDescription: String(localized: "No box is open.")) }
        return Data(try await bridge.render(name, args: overrides[name] ?? [:], format: format).utf8)
    }

    private func loadSpec() async {
        guard let bridge, let selection else { return }
        do {
            let spec = try await bridge.spec(selection)
            guard spec.name == self.selection else { return }
            self.spec = spec
            scheduleRender(delay: .zero)
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func scheduleRender(delay: Duration = .milliseconds(250)) {
        renderTask?.cancel()
        renderTask = Task {
            try? await Task.sleep(for: delay)
            guard !Task.isCancelled, let bridge, let name = spec?.name else { return }
            isRendering = true
            defer { if !Task.isCancelled { isRendering = false } }
            do {
                let svg = try await bridge.render(name, args: overrides[name] ?? [:], format: "svg")
                guard !Task.isCancelled else { return }
                self.svg = svg
                error = nil
                if showsAssembly {
                    do {
                        let args = overrides[name] ?? [:]
                        let assembly = try await bridge.assemble(name, args: args)
                        guard !Task.isCancelled else { return }
                        self.assembly = assembly
                        assemblyKey = name + "|" + args.sorted { $0.key < $1.key }.map { "\($0.key)=\($0.value)" }.joined(separator: ";")
                        assemblyError = nil
                    } catch {
                        guard !Task.isCancelled else { return }
                        assembly = nil
                        assemblyError = error.localizedDescription
                    }
                }
            } catch {
                guard !Task.isCancelled else { return }
                self.error = error.localizedDescription
            }
        }
    }
}


/// The gallery's 3D cards, built before the gallery shows: each box's scene made, its shapes
/// triangulated and uploaded, off the main thread, so a card scrolling into view only attaches it
/// (a card building its scene on the main thread made scrolling stutter). The boxes are kept on disk
/// as long as the code that makes them is the same, so later launches skip Python.
actor GalleryScenes {
    static let shared = GalleryScenes()
    private let folder: URL
    private let renderer = SCNRenderer(device: MTLCreateSystemDefaultDevice(), options: nil)

    init() {
        let root = URL.cachesDirectory.appending(path: Bundle.main.bundleIdentifier ?? "LaserBox").appending(path: "Gallery")
        var hash = SHA256()   // the assembly code and the app's defaults decide the boxes
        for file in ["assembly.py", "bridge.py"] {
            if let url = Bundle.main.url(forResource: file, withExtension: nil), let data = try? Data(contentsOf: url) {
                hash.update(data: data)
            }
        }
        let stamp = hash.finalize().prefix(8).map { String(format: "%02x", $0) }.joined()
        folder = root.appending(path: stamp)
        let files = FileManager.default
        for old in (try? files.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)) ?? [] where old.lastPathComponent != stamp {
            try? files.removeItem(at: old)
        }
        try? files.createDirectory(at: folder, withIntermediateDirectories: true)
    }

    func cached(_ name: String) -> Assembly? {
        (try? Data(contentsOf: file(name))).flatMap { try? JSONDecoder().decode(Assembly.self, from: $0) }
    }

    func keep(_ assembly: Assembly, as name: String) {
        try? JSONEncoder().encode(assembly).write(to: file(name))
    }

    func stage(for assembly: Assembly) -> AssemblyStage {
        let stage = AssemblyStage.gallery(assembly)
        _ = renderer.prepare(stage.scene, shouldAbortBlock: nil)
        return stage
    }

    private func file(_ name: String) -> URL { folder.appending(path: name + ".json") }
}
