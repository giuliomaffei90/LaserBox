import Foundation
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
