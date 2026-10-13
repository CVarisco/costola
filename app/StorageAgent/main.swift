import Foundation

guard let executableURL = Bundle.main.executableURL else {
    FileHandle.standardError.write(Data("Cannot locate the Costola launcher.\n".utf8))
    exit(1)
}
let appURL = executableURL.resolvingSymlinksInPath()
    .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
Task {
    do {
        let bytes: Data
        if CommandLine.arguments.dropFirst() == ["--probe"] {
            (_, bytes) = try BundleWorker.probe(appURL: appURL)
        } else if CommandLine.arguments.count == 1 {
            let requestID = UUID().uuidString
            let input = try JSONSerialization.data(withJSONObject: [
                "protocol_version": 1, "request_id": requestID, "command": "monitor",
            ])
            bytes = try BundleWorker.exchange(appURL: appURL, input: input, requestID: requestID)
            if let response = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
               let data = response["data"] as? [String: Any], data["notify"] as? Bool == true {
                do { try await Notifications.sendStorageAttention() }
                catch { FileHandle.standardError.write(Data("Could not deliver the storage notification. Open Costola to inspect status.\n".utf8)) }
            }
        } else {
            throw NSError(domain: "CostolaAgent", code: 1, userInfo: [NSLocalizedDescriptionKey: "Usage: CostolaAgent [--probe]"])
        }
        FileHandle.standardOutput.write(bytes)
        FileHandle.standardOutput.write(Data([10]))
        exit(0)
    } catch {
        FileHandle.standardError.write(Data((error.localizedDescription + "\n").utf8))
        exit(1)
    }
}
dispatchMain()
