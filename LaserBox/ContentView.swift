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
                GalleryView(model: model, category: category ?? .all) { path.append($0) }
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
        case "Tests": "testtube.2"
        default: "square.grid.3x3"
        }
    }
}

struct GalleryView: View {
    let model: BoxModel
    let category: Category
    let open: (GeneratorInfo) -> Void
    @State private var search = ""
    @AppStorage("cardSize") private var cardSize = 220.0

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
                ForEach(model.preparing == nil ? sections : []) { group in
                    VStack(alignment: .leading, spacing: 14) {
                        if category == .all {
                            Text(group.title).font(.title2.bold())
                        }
                        if !group.description.isEmpty {
                            Text(group.description).foregroundStyle(.secondary)
                        }
                        LazyVGrid(columns: [GridItem(.adaptive(minimum: cardSize, maximum: cardSize * 1.3), spacing: 20, alignment: .top)],
                                  alignment: .leading, spacing: 26) {
                            ForEach(group.generators) { generator in
                                if generator.assembled {
                                    GeneratorCard(generator: generator, model: model) { open(generator) }
                                } else {
                                    NavigationLink(value: generator) { GeneratorCard(generator: generator) }
                                        .buttonStyle(.plain)
                                }
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
            } else if let preparing = model.preparing {
                VStack(spacing: 12) {
                    ProgressView(value: Double(preparing.done), total: Double(max(preparing.of, 1)))
                        .frame(width: 280)
                    Text("Preparing the 3D previews… \(preparing.done) of \(preparing.of)")
                        .foregroundStyle(.secondary)
                        .monospacedDigit()
                }
            } else if sections.isEmpty {
                ContentUnavailableView.search(text: search)
            }
        }
        .navigationTitle(title)
        .navigationSubtitle(model.groups.isEmpty ? "" : String(localized: "\(sections.reduce(0) { $0 + $1.generators.count }) boxes"))
        .searchable(text: $search, prompt: "Search Boxes")
        .toolbar {
            ToolbarItem {
                Slider(value: $cardSize, in: 140...420) {
                    Text("Card Size")
                } minimumValueLabel: {
                    Image(systemName: "square.grid.3x3").accessibilityHidden(true)
                } maximumValueLabel: {
                    Image(systemName: "square.grid.2x2").accessibilityHidden(true)
                }
                .labelsHidden()
                .frame(width: 150)
                .padding(.horizontal, 8)
                .help("Size of the boxes in the gallery")
            }
        }
    }
}

struct GeneratorCard: View {
    let generator: GeneratorInfo
    var model: BoxModel? = nil           // set for boxes shown as a live 3D model
    var open: (() -> Void)? = nil
    @State private var hovering = false
    @State private var yaw: CGFloat = 0
    @State private var pitch: CGFloat = 0
    @State private var dragStart: (CGFloat, CGFloat)?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Color.clear
                .aspectRatio(1, contentMode: .fit)
                .overlay {
                    if let model {
                        Group {
                            if let stage = model.galleryStages[generator.name] {
                                StageView(stage: stage, yaw: yaw, pitch: pitch)
                            } else {
                                ProgressView()
                            }
                        }
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .background(.fill.tertiary)
                        .task { await model.loadGalleryStage(generator.name) }
                        // Drag turns the box; a plain click opens it.
                        .contentShape(.rect)
                        .gesture(DragGesture(minimumDistance: 3).onChanged { value in
                            if dragStart == nil { dragStart = (yaw, pitch) }
                            yaw = dragStart!.0 + value.translation.width / 80
                            pitch = max(-1.2, min(1.2, dragStart!.1 + value.translation.height / 120))
                        }.onEnded { _ in dragStart = nil })
                        .onTapGesture { open?() }
                    } else {
                        SampleImage(name: generator.name)
                    }
                }
                .clipShape(.rect(cornerRadius: 12))
                .shadow(color: .black.opacity(hovering ? 0.18 : 0.06), radius: hovering ? 10 : 3, y: hovering ? 4 : 1)
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

/// The isometric illustration of a box; the web site's photo or the default drawing as fallbacks.
struct SampleImage: View {
    let name: String
    var photo = false  // true shows the real photo instead, when there is one
    private static let cache = NSCache<NSString, NSImage>()
    private static let folder = Bundle.main.resourceURL!.appending(path: "Runtime/samples")

    static func hasPhoto(_ name: String) -> Bool { image("\(name).jpg") != nil }

    var body: some View {
        if photo, let photo = Self.image("\(name).jpg") {
            Image(nsImage: photo).resizable().scaledToFill()
        } else if let illustration = Self.image("\(name).png") {
            Image(nsImage: illustration).resizable().scaledToFit().padding(6)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(.fill.tertiary)
        } else if let photo = Self.image("\(name).jpg") {
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
