import XCTest
@testable import Costola

final class EngineProcessTests: XCTestCase {
    func testLargeStderrDoesNotBlockARealWorkerProcess() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let worker = root.appendingPathComponent("Contents/Helpers/CostolaWorker.app")
        let executable = worker.appendingPathComponent("Contents/MacOS/CostolaWorker")
        try FileManager.default.createDirectory(at: executable.deletingLastPathComponent(), withIntermediateDirectories: true)
        let source = root.appendingPathComponent("fixture.swift")
        try #"""
        import Foundation
        let request = try JSONSerialization.jsonObject(with: FileHandle.standardInput.readDataToEndOfFile()) as! [String: Any]
        FileHandle.standardError.write(Data(repeating: 65, count: 1024 * 1024))
        let data = try JSONSerialization.data(withJSONObject: ["protocol_version": 1, "request_id": request["request_id"]!, "type": "result", "success": true, "data": ["revision": 0]])
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data([10]))
        """#.write(to: source, atomically: true, encoding: .utf8)
        let plist: [String: Any] = ["CFBundleIdentifier": "com.cvarisco.costola.fixture.worker",
                                    "CFBundleExecutable": "CostolaWorker", "CFBundlePackageType": "APPL"]
        try PropertyListSerialization.data(fromPropertyList: plist, format: .xml, options: 0)
            .write(to: worker.appendingPathComponent("Contents/Info.plist"))
        try run("/usr/bin/xcrun", ["swiftc", source.path, "-o", executable.path])
        try run("/usr/bin/codesign", ["--force", "--sign", "-", worker.path])
        let input = Data(#"{"protocol_version":1,"request_id":"large-stderr","command":"info"}"#.utf8)
        let result = try BundleWorker.exchange(appURL: root, input: input, requestID: "large-stderr")
        let response = try XCTUnwrap(JSONSerialization.jsonObject(with: result) as? [String: Any])
        XCTAssertEqual(response["success"] as? Bool, true)
    }

    private func run(_ executable: String, _ arguments: [String]) throws {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = arguments
        let diagnostics = Pipe()
        process.standardError = diagnostics
        try process.run()
        let message = diagnostics.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        XCTAssertEqual(process.terminationStatus, 0, String(decoding: message, as: UTF8.self))
    }
}
