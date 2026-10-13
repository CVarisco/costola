import Foundation

guard let executableURL = Bundle.main.executableURL else {
    FileHandle.standardError.write(Data("Cannot locate the Costola launcher.\n".utf8))
    exit(1)
}
let appURL = executableURL
    .resolvingSymlinksInPath()
    .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
do {
    let (_, bytes) = try BundleWorker.probe(appURL: appURL)
    FileHandle.standardOutput.write(bytes)
    FileHandle.standardOutput.write(Data([10]))
} catch {
    FileHandle.standardError.write(Data((error.localizedDescription + "\n").utf8))
    exit(1)
}
