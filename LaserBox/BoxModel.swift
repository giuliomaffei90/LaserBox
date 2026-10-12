import AppKit
import Observation

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
    /// Assembled boxes with default parameters, for the gallery cards.
    var galleryAssemblies: [String: Assembly] = [:]
    /// The gallery cards' pictures of them (see GalleryPictures).
    var galleryPictures: [String: NSImage] = [:]

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
        }
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

    func loadGalleryAssembly(_ name: String) async {
        guard let bridge, galleryAssemblies[name] == nil else { return }
        if let assembly = try? await bridge.assemble(name, args: [:]) {
            galleryAssemblies[name] = assembly
        }
    }

    func loadGalleryPicture(_ name: String) async {
        guard galleryPictures[name] == nil else { return }
        if let picture = await GalleryPictures.shared.cached(name) {
            galleryPictures[name] = picture
            return
        }
        await loadGalleryAssembly(name)
        guard let assembly = galleryAssemblies[name] else { return }
        galleryPictures[name] = await GalleryPictures.shared.render(name, assembly)
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


/// The gallery's 3D cards as pictures, rendered one at a time off the main thread and kept on disk
/// for this build of the app: a live SceneKit view per card made scrolling stutter. A card turns
/// live only while the pointer is on it.
actor GalleryPictures {
    static let shared = GalleryPictures()
    private let folder: URL

    init() {
        let root = URL.cachesDirectory.appending(path: Bundle.main.bundleIdentifier ?? "LaserBox").appending(path: "Gallery")
        // Another build may draw any box differently: its pictures go in a folder of their own.
        let built = (try? Bundle.main.executableURL?.resourceValues(forKeys: [.contentModificationDateKey]))?
            .contentModificationDate ?? .distantPast
        let stamp = String(Int(built.timeIntervalSince1970))
        folder = root.appending(path: stamp)
        let files = FileManager.default
        for old in (try? files.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)) ?? [] where old.lastPathComponent != stamp {
            try? files.removeItem(at: old)
        }
        try? files.createDirectory(at: folder, withIntermediateDirectories: true)
    }

    func cached(_ name: String) -> NSImage? {
        NSImage(contentsOf: file(name))
    }

    func render(_ name: String, _ assembly: Assembly) -> NSImage {
        let picture = AssemblyStage.galleryPicture(of: assembly, pixels: 640)
        if let tiff = picture.tiffRepresentation,
           let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) {
            try? png.write(to: file(name))
        }
        return picture
    }

    private func file(_ name: String) -> URL { folder.appending(path: name + ".png") }
}
