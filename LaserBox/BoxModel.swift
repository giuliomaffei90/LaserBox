import AppKit
import CryptoKit
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
    /// The pictures being prepared at launch, done of all; nil once the gallery can show.
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

    /// Every 3D card's picture, ready before the gallery shows and kept for the whole session: from
    /// disk, or rendered (and kept there). A few at a time, so Python assembles the next boxes while
    /// SceneKit draws one.
    private func prepareGallery() async {
        let names = Set(groups.flatMap(\.generators).filter(\.assembled).map(\.name)).sorted()
        preparing = (0, names.count)
        await withTaskGroup(of: Void.self) { group in
            var next = names.makeIterator()
            for _ in 0..<3 {
                if let name = next.next() { group.addTask { await self.loadGalleryPicture(name) } }
            }
            for await _ in group {
                preparing?.done += 1
                if let name = next.next() { group.addTask { await self.loadGalleryPicture(name) } }
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

    func loadGalleryAssembly(_ name: String) async {
        guard let bridge, galleryAssemblies[name] == nil, !Task.isCancelled else { return }
        if let assembly = try? await bridge.assemble(name, args: [:]) {
            galleryAssemblies[name] = assembly
        }
    }

    /// A card's picture, from disk or rendered. A card scrolled away (its task cancelled) gives up its
    /// turn, so the ones on screen don't wait behind all those scrolled past.
    func loadGalleryPicture(_ name: String) async {
        guard galleryPictures[name] == nil else { return }
        if let picture = await GalleryPictures.shared.cached(name) {
            galleryPictures[name] = picture
            return
        }
        guard !Task.isCancelled else { return }
        await loadGalleryAssembly(name)
        guard !Task.isCancelled, let assembly = galleryAssemblies[name] else { return }
        if let picture = await GalleryPictures.shared.render(name, assembly) {
            galleryPictures[name] = picture
        }
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


/// The gallery's 3D cards as pictures, rendered one at a time off the main thread and kept on disk:
/// a live SceneKit view per card made scrolling stutter. A card turns live only while it's turned.
actor GalleryPictures {
    static let shared = GalleryPictures()
    /// Bump when the pictures' look changes (lights, materials, framing).
    private static let look = 1
    private let folder: URL

    init() {
        let root = URL.cachesDirectory.appending(path: Bundle.main.bundleIdentifier ?? "LaserBox").appending(path: "Gallery")
        // The pictures hold as long as the boxes come out the same: the assembly code, the app's
        // defaults and the look. Other pictures go.
        var hash = SHA256()
        for file in ["assembly.py", "bridge.py"] {
            if let url = Bundle.main.url(forResource: file, withExtension: nil), let data = try? Data(contentsOf: url) {
                hash.update(data: data)
            }
        }
        hash.update(data: Data("\(Self.look)".utf8))
        let stamp = hash.finalize().prefix(8).map { String(format: "%02x", $0) }.joined()
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

    func render(_ name: String, _ assembly: Assembly) -> NSImage? {
        guard !Task.isCancelled else { return nil }   // its card was scrolled away while it waited
        let picture = AssemblyStage.galleryPicture(of: assembly, pixels: 640)
        if let tiff = picture.tiffRepresentation,
           let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) {
            try? png.write(to: file(name))
        }
        return picture
    }

    private func file(_ name: String) -> URL { folder.appending(path: name + ".png") }
}
