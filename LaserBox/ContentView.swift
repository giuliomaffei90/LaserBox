import SwiftUI

enum Category: Hashable {
    case all
    case group(String)
}

struct ContentView: View {
    @State private var model = BoxModel()
    @State private var category: Category? = .all
    @State private var path: [GeneratorInfo] = []
    @State private var columns: NavigationSplitViewVisibility = .all

    var body: some View {
        NavigationSplitView(columnVisibility: $columns) {
            List(selection: $category) {
                Label("All Boxes", systemImage: "square.grid.2x2")
                    .tag(Category.all)
                Section("Categories") {
                    ForEach(model.groups) { group in
                        Label(group.title, systemImage: symbol(for: group.name))
                            .badge(group.generators.count)
                            .tag(Category.group(group.name))
                    }
                }
            }
            .navigationSplitViewColumnWidth(min: 200, ideal: 230)
        } detail: {
            NavigationStack(path: $path) {
                GalleryView(model: model, category: category ?? .all)
                    .navigationDestination(for: GeneratorInfo.self) { EditorView(model: model, generator: $0) }
            }
        }
        // The editor gets the whole window; back in the gallery the categories return.
        .onChange(of: path) { columns = path.isEmpty ? .all : .detailOnly }
        .onChange(of: category) { path = [] }
        .task { await model.start() }
    }

    private func symbol(for group: String) -> String {
        switch group {
        case "Box": "shippingbox"
        case "FlexBox": "cylinder"
        case "Tray": "tray.2"
        case "Shelf": "books.vertical"
        case "WallMounted": "rectangle.on.rectangle.angled"
        case "Holes": "circle.grid.3x3"
        case "Part": "puzzlepiece"
        case "Unstable": "flask"
        default: "square.grid.3x3"
        }
    }
}

struct GalleryView: View {
    let model: BoxModel
    let category: Category
    @State private var search = ""

    private var sections: [GeneratorGroup] {
        let groups = switch category {
        case .all: model.groups
        case .group(let name): model.groups.filter { $0.name == name }
        }
        guard !search.isEmpty else { return groups }
        return groups.compactMap { group in
            let matches = group.generators.filter {
                $0.title.localizedCaseInsensitiveContains(search) || $0.doc.localizedCaseInsensitiveContains(search)
                    || $0.name.localizedCaseInsensitiveContains(search)
            }
            return matches.isEmpty ? nil : GeneratorGroup(name: group.name, title: group.title, description: group.description, generators: matches)
        }
    }

    private var title: String {
        if case .group(let name) = category, let group = model.groups.first(where: { $0.name == name }) { return group.title }
        return String(localized: "All Boxes")
    }

    var body: some View {
        let sections = sections
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 36) {
                ForEach(sections) { group in
                    VStack(alignment: .leading, spacing: 14) {
                        if category == .all {
                            Text(group.title).font(.title2.bold())
                        }
                        if !group.description.isEmpty {
                            Text(group.description).foregroundStyle(.secondary)
                        }
                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 190, maximum: 260), spacing: 20, alignment: .top)],
                                  alignment: .leading, spacing: 26) {
                            ForEach(group.generators) { generator in
                                NavigationLink(value: generator) { GeneratorCard(generator: generator) }
                                    .buttonStyle(.plain)
                            }
                        }
                    }
                }
            }
            .padding(24)
        }
        .overlay {
            if let error = model.startupError {
                ContentUnavailableView("Can’t Start boxes.py", systemImage: "exclamationmark.triangle", description: Text(error))
            } else if model.groups.isEmpty {
                ProgressView("Loading the Boxes…")
            } else if sections.isEmpty {
                ContentUnavailableView.search(text: search)
            }
        }
        .navigationTitle(title)
        .navigationSubtitle(model.groups.isEmpty ? "" : String(localized: "\(sections.reduce(0) { $0 + $1.generators.count }) boxes"))
        .searchable(text: $search, prompt: "Search Boxes")
    }
}

struct GeneratorCard: View {
    let generator: GeneratorInfo
    @State private var hovering = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Color.clear
                .aspectRatio(1, contentMode: .fit)
                .overlay { SampleImage(name: generator.name) }
                .clipShape(.rect(cornerRadius: 12))
                .shadow(color: .black.opacity(hovering ? 0.25 : 0.12), radius: hovering ? 10 : 4, y: hovering ? 4 : 1)
                .scaleEffect(hovering ? 1.02 : 1)
                .padding(.bottom, 4)
            Text(generator.title)
                .font(.headline)
            Text(generator.doc)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .lineLimit(2, reservesSpace: true)
        }
        .contentShape(.rect)
        .onHover { hovering in withAnimation(.snappy(duration: 0.2)) { self.hovering = hovering } }
        .accessibilityElement(children: .combine)
        .help(generator.doc)
    }
}

/// The web site's photo of a box, or its default drawing when nobody has photographed one yet.
struct SampleImage: View {
    let name: String
    private static let cache = NSCache<NSString, NSImage>()
    private static let folder = Bundle.main.resourceURL!.appending(path: "Runtime/samples")

    var body: some View {
        if let photo = Self.image("\(name).jpg") {
            Image(nsImage: photo).resizable().scaledToFill()
        } else if let drawing = Self.image("\(name).svg") {
            Image(nsImage: drawing).resizable().scaledToFit().padding(14)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(.white)
        } else {
            Image(systemName: "shippingbox").font(.largeTitle).foregroundStyle(.tertiary)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(.quaternary)
        }
    }

    private static func image(_ file: String) -> NSImage? {
        if let cached = cache.object(forKey: file as NSString) { return cached }
        guard let image = NSImage(contentsOf: folder.appending(path: file)) else { return nil }
        cache.setObject(image, forKey: file as NSString)
        return image
    }
}
