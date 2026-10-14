import SwiftUI

/// FrontPanel's layout: one command per line, "outline w h" starting a panel, then the holes in it
/// (rect, circle, mountinghole, text, nema) with their values in order. Comments are not kept.
struct FrontPanelLayout {
    struct Panel {
        var size: [String]     // width, height
        var holes: [[String]]  // each: its command, then its values
    }
    var panels: [Panel] = []

    init(_ text: String) {
        for line in text.split(whereSeparator: \.isNewline) {
            let words = Self.words(line.prefix { $0 != "#" })  // the generator drops from # on, quotes or not
            guard let command = words.first?.lowercased() else { continue }
            let values = Array(words.dropFirst())
            if command == "outline" {
                panels.append(Panel(size: Self.padded(values, ["100", "100"]), holes: []))
            } else if let kind = HoleKind.all.first(where: { $0.command == command }) {
                if panels.isEmpty { panels.append(Panel(size: ["100", "100"], holes: [])) }
                panels[panels.count - 1].holes.append([command] + Self.padded(values, kind.fields.map(\.default)))
            }
        }
    }

    var text: String {
        panels.map { panel in
            ([["outline"] + panel.size] + panel.holes).map { $0.map(Self.quoted).joined(separator: " ") }.joined(separator: "\n")
        }.joined(separator: "\n\n")
    }

    /// Value i of panel p's size (hole nil) or of its hole h (0 is the command); "" once removed.
    subscript(p: Int, h: Int?, i: Int) -> String {
        get {
            guard panels.indices.contains(p) else { return "" }
            let words = h.map { panels[p].holes.indices.contains($0) ? panels[p].holes[$0] : [] } ?? panels[p].size
            return words.indices.contains(i) ? words[i] : ""
        }
        set {
            guard panels.indices.contains(p) else { return }
            if let h {
                if panels[p].holes.indices.contains(h), panels[p].holes[h].indices.contains(i) { panels[p].holes[h][i] = newValue }
            } else if panels[p].size.indices.contains(i) {
                panels[p].size[i] = newValue
            }
        }
    }

    /// A hole of this kind in the middle of panel p.
    func newHole(_ kind: HoleKind, in p: Int) -> [String] {
        let middle = panels[p].size.map { String(format: "%g", (Double($0) ?? 0) / 2) }
        return [kind.command] + middle + kind.fields.dropFirst(2).map(\.default)
    }

    private static func padded(_ values: [String], _ defaults: [String]) -> [String] {
        defaults.indices.map { values.indices.contains($0) ? values[$0] : defaults[$0] }
    }

    /// The line split as the generator's shlex does: on spaces, quotes grouping, backslash escaping.
    private static func words(_ line: Substring) -> [String] {
        var words: [String] = [], word = "", inWord = false, quote: Character?, escaped = false
        for c in line {
            if escaped {
                word.append(c); escaped = false
            } else if c == "\\" && quote != "'" {
                escaped = true; inWord = true
            } else if let q = quote {
                if c == q { quote = nil } else { word.append(c) }
            } else if c == "\"" || c == "'" {
                quote = c; inWord = true
            } else if c.isWhitespace {
                if inWord { words.append(word); word = ""; inWord = false }
            } else {
                word.append(c); inWord = true
            }
        }
        if inWord { words.append(word) }
        return words
    }

    private static func quoted(_ word: String) -> String {
        if !word.isEmpty, word.allSatisfy({ $0.isLetter || $0.isNumber || ".-+|_".contains($0) }) { return word }
        return "\"" + word.replacing("\\", with: "\\\\").replacing("\"", with: "\\\"") + "\""
    }
}

/// A kind of hole FrontPanel draws, and its values in the generator's order.
struct HoleKind {
    enum FieldType { case number, toggle, text, align, nema }
    struct Field {
        let label: LocalizedStringKey
        let `default`: String
        var type = FieldType.number
    }
    let command: String
    let name: LocalizedStringKey
    let fields: [Field]

    static let all = [
        HoleKind(command: "rect", name: "Rectangle", fields: [
            Field(label: "X", default: "50"), Field(label: "Y", default: "50"),
            Field(label: "Width", default: "20"), Field(label: "Height", default: "10"),
            Field(label: "Corner radius", default: "0"),
            Field(label: "Centered horizontally", default: "True", type: .toggle),
            Field(label: "Centered vertically", default: "True", type: .toggle)]),
        HoleKind(command: "circle", name: "Round hole", fields: [
            Field(label: "X", default: "50"), Field(label: "Y", default: "50"),
            Field(label: "Radius", default: "3")]),
        HoleKind(command: "mountinghole", name: "Mounting hole", fields: [
            Field(label: "X", default: "50"), Field(label: "Y", default: "50"),
            Field(label: "Shaft diameter", default: "3"), Field(label: "Head diameter", default: "6"),
            Field(label: "Angle", default: "0")]),
        HoleKind(command: "text", name: "Text", fields: [
            Field(label: "X", default: "50"), Field(label: "Y", default: "50"),
            Field(label: "Size", default: "5"), Field(label: "Text", default: "Text", type: .text),
            Field(label: "Angle", default: "0"), Field(label: "Alignment", default: "bottom|left", type: .align)]),
        HoleKind(command: "nema", name: "NEMA motor", fields: [
            Field(label: "X", default: "50"), Field(label: "Y", default: "50"),
            Field(label: "Size", default: "17", type: .nema), Field(label: "Screw size", default: "0")]),
    ]
    static let nemaSizes = ["8", "11", "14", "16", "17", "23", "24", "34", "42"]  // boxes.py's nema_sizes

    static func named(_ command: String) -> HoleKind { all.first { $0.command == command } ?? all[0] }
}

/// FrontPanel's layout edited as one section per panel: its size, then its holes, each with its kind
/// and labelled values, instead of as text.
struct FrontPanelSections: View {
    @Binding var text: String

    var body: some View {
        let layout = FrontPanelLayout(text)
        ForEach(layout.panels.indices, id: \.self) { p in
            Section("Panel \(p + 1)") {
                TextField(text: value(p, nil, 0)) { Text("Width") }
                    .multilineTextAlignment(.trailing)
                TextField(text: value(p, nil, 1)) { Text("Height") }
                    .multilineTextAlignment(.trailing)
                ForEach(layout.panels[p].holes.indices, id: \.self) { h in
                    hole(p, h, layout.panels[p].holes[h])
                }
                HStack {
                    Menu("Add Hole") {
                        ForEach(HoleKind.all, id: \.command) { kind in
                            Button(kind.name) { edit { $0.panels[p].holes.append($0.newHole(kind, in: p)) } }
                        }
                    }
                    .fixedSize()
                    Spacer()
                    Button("Remove Panel", role: .destructive) { edit { $0.panels.remove(at: p) } }
                        .disabled(layout.panels.count == 1)
                }
            }
        }
        Section {
            Button("Add Panel") { edit { $0.panels.append(.init(size: ["100", "100"], holes: [])) } }
        } footer: {
            Text("X and Y are in mm from the panel's bottom left corner.")
        }
    }

    private func hole(_ p: Int, _ h: Int, _ words: [String]) -> some View {
        let kind = HoleKind.named(words[0])
        return DisclosureGroup {
            Picker("Kind", selection: Binding { kind.command } set: { command in
                edit { layout in
                    let new = HoleKind.named(command)
                    layout.panels[p].holes[h] = [command] + layout.panels[p].holes[h][1...2] + new.fields.dropFirst(2).map(\.default)
                }
            }) {
                ForEach(HoleKind.all, id: \.command) { Text($0.name).tag($0.command) }
            }
            ForEach(kind.fields.indices, id: \.self) { i in
                field(kind.fields[i], value(p, h, i + 1))
            }
            Button("Remove Hole", role: .destructive) { edit { $0.panels[p].holes.remove(at: h) } }
        } label: {
            HStack {
                Text(kind.name)
                Spacer()
                Text("\(words[1]), \(words[2])").foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder private func field(_ field: HoleKind.Field, _ value: Binding<String>) -> some View {
        switch field.type {
        case .number:
            TextField(text: value) { Text(field.label) }
                .multilineTextAlignment(.trailing)
        case .text:
            TextField(text: value) { Text(field.label) }
        case .toggle:  // the generator's str_to_bool
            Toggle(field.label, isOn: Binding {
                ["true", "1", "t", "y", "yes"].contains(value.wrappedValue.lowercased())
            } set: { value.wrappedValue = $0 ? "True" : "False" })
        case .nema:
            Picker(field.label, selection: value) {
                ForEach(HoleKind.nemaSizes, id: \.self) { Text($0).tag($0) }
            }
        case .align:  // "vertical|horizontal", e.g. bottom|left
            let parts = value.wrappedValue.split(separator: "|").map(String.init)
            let vertical = parts.first { ["top", "middle", "bottom"].contains($0) } ?? "bottom"
            let horizontal = parts.first { ["left", "center", "right"].contains($0) } ?? "left"
            Picker("Vertical alignment", selection: Binding { vertical } set: { value.wrappedValue = $0 + "|" + horizontal }) {
                Text("Top").tag("top"); Text("Middle").tag("middle"); Text("Bottom").tag("bottom")
            }
            Picker("Horizontal alignment", selection: Binding { horizontal } set: { value.wrappedValue = vertical + "|" + $0 }) {
                Text("Left").tag("left"); Text("Center").tag("center"); Text("Right").tag("right")
            }
        }
    }

    private func value(_ p: Int, _ h: Int?, _ i: Int) -> Binding<String> {
        Binding { FrontPanelLayout(text)[p, h, i] } set: { new in edit { $0[p, h, i] = new } }
    }

    private func edit(_ change: (inout FrontPanelLayout) -> Void) {
        var layout = FrontPanelLayout(text)
        change(&layout)
        text = layout.text
    }
}
