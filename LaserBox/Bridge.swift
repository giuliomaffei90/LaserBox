import Foundation

struct GeneratorGroup: Decodable, Identifiable {
    let name, title, description: String
    let generators: [GeneratorInfo]
    var id: String { name }
}

struct GeneratorInfo: Decodable, Identifiable, Hashable {
    let name, title, doc: String
    let assembled: Bool  // has a 3D assembly recipe
    var id: String { name }
}

struct GeneratorSpec: Decodable {
    let name, title, doc, description: String
    let groups: [ArgGroup]
}

struct ArgGroup: Decodable, Identifiable {
    let title: String
    let args: [Arg]
    let advanced: Bool
    var id: String { title }
}

struct Arg: Decodable, Identifiable {
    let name, label, help, `default`, kind: String
    let choices: [Choice]?
    var id: String { name }
}

struct Choice: Decodable {
    let value, label: String
}

/// One flat piece of the assembled box: polygon rings in mm (first ring outer, the rest holes),
/// extruded by t along side·(u×v) and placed at origin. `lid` marks a lid; `decoration` (its kind) other pieces
/// the view can hide: what goes in the box but isn't cut, removable panels.
struct Piece: Codable {
    let rings: [[[Double]]]
    let origin, u, v: [Double]
    let side: Int
    let t: Double
    var part: Int?    // the placed part it was cut from, shared by its pieces; none for decorations not cut
    var decoration: String?
    var lid: Bool?
    var clear: Bool?  // always clear acrylic, whatever the material (a display case's glass)
    var joint: Int?   // the joint (in Assembly.joints) it moves with
}

/// What moves a hinged or sliding part: "hinge" turns about `axis` through `at` (degrees, right-handed),
/// "slide" moves along `axis` (mm), within `range` from where the pieces are placed.
struct Joint: Codable {
    let kind: String
    var at: [Double]?
    let axis: [Double]
    let range: [Double]
    var start: Double?
}

struct Assembly: Codable {
    let pieces: [Piece]
    var joints: [Joint]?
    var turn: Double?  // degrees about the vertical the gallery shows it turned by
    var galleryLids: Bool?  // the gallery shows its lids (it leaves them out otherwise)
}

struct BridgeError: LocalizedError {
    let errorDescription: String?
}

/// Runs bundle/Resources/bridge.py with the bundled Python and talks to it one JSON line at a time.
final class Bridge: @unchecked Sendable {
    private let process = Process()
    private let input = Pipe(), output = Pipe()
    private let queue = DispatchQueue(label: "bridge")  // one request at a time, answers stay in order
    private var buffer = Data()

    init() throws {
        let resources = Bundle.main.resourceURL!
        let python = resources.appending(path: "Runtime/python/bin/python3")
        guard FileManager.default.isExecutableFile(atPath: python.path) else {
            throw BridgeError(errorDescription: String(localized: "Python isn’t included in the app. Run scripts/bundle-runtime.sh and build again."))
        }
        process.executableURL = python
        process.arguments = ["-s", "-B", resources.appending(path: "bridge.py").path]
        process.environment = [
            "PYTHONPATH": resources.appending(path: "Runtime/site").path,
            "LASERBOX_LANG": Bundle.main.preferredLocalizations.first ?? "en",
        ]
        process.standardInput = input
        process.standardOutput = output
        try process.run()
    }

    func list() async throws -> [GeneratorGroup] {
        struct Reply: Decodable { let groups: [GeneratorGroup] }
        return try await send(["cmd": "list"], as: Reply.self).groups
    }

    func spec(_ name: String) async throws -> GeneratorSpec {
        try await send(["cmd": "args", "name": name], as: GeneratorSpec.self)
    }

    func render(_ name: String, args: [String: String], format: String) async throws -> String {
        struct Reply: Decodable { let data: String }
        return try await send(["cmd": "render", "name": name, "args": args, "format": format], as: Reply.self).data
    }

    func assemble(_ name: String, args: [String: String]) async throws -> Assembly {
        try await send(["cmd": "assemble", "name": name, "args": args], as: Assembly.self)
    }

    private func send<T: Decodable>(_ request: [String: Any], as: T.Type) async throws -> T {
        let line = try JSONSerialization.data(withJSONObject: request) + [0x0A]
        let reply = try await withCheckedThrowingContinuation { (c: CheckedContinuation<Data, Error>) in
            queue.async {
                c.resume(with: Result {
                    try self.input.fileHandleForWriting.write(contentsOf: line)
                    return try self.readLine()
                })
            }
        }
        if let error = (try? JSONSerialization.jsonObject(with: reply) as? [String: Any])?["error"] as? String {
            throw BridgeError(errorDescription: error)
        }
        return try JSONDecoder().decode(T.self, from: reply)
    }

    private func readLine() throws -> Data {
        while true {
            if let end = buffer.firstIndex(of: 0x0A) {
                let line = buffer[..<end]
                buffer = buffer[(end + 1)...]
                return Data(line)
            }
            let chunk = output.fileHandleForReading.availableData
            if chunk.isEmpty { throw BridgeError(errorDescription: String(localized: "The boxes.py engine quit unexpectedly.")) }
            buffer += chunk
        }
    }
}
