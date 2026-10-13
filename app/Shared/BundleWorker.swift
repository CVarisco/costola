import Foundation
import Security

struct WorkerInfo: Decodable {
    let product: String
    let capabilities: [String]
    let pythonVersion: String
    let architecture: String
    let frozen: Bool
}

struct WorkerResult: Decodable {
    struct Failure: Decodable { let code: String; let message: String }
    let protocolVersion: Int
    let requestId: String?
    let type: String
    let success: Bool
    let data: WorkerInfo?
    let error: Failure?
}

enum WorkerError: LocalizedError {
    case missing, signature(String, OSStatus), failed(String), invalidResponse

    var errorDescription: String? {
        switch self {
        case .missing: return "The bundled Costola worker is missing. Reinstall the app."
        case .signature(let component, let status):
            return "The Costola code signature could not be verified (\(component), \(status)). Reinstall the app."
        case .failed(let message): return message
        case .invalidResponse: return "The Costola worker returned an incompatible or incomplete response."
        }
    }
}

enum BundleWorker {
    static func decode(_ bytes: Data, requestID: String) throws -> WorkerResult {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let result = try decoder.decode(WorkerResult.self, from: bytes)
        guard result.protocolVersion == 1, result.requestId == requestID,
              result.type == "result" else { throw WorkerError.invalidResponse }
        guard result.success else {
            throw WorkerError.failed(result.error?.message ?? "The worker failed.")
        }
        guard let info = result.data, info.product == "Costola", info.frozen else {
            throw WorkerError.invalidResponse
        }
        return result
    }

    static func probe(appURL: URL) throws -> (WorkerResult, Data) {
        let requestID = UUID().uuidString
        let input = try JSONSerialization.data(withJSONObject: [
            "protocol_version": 1, "request_id": requestID, "command": "info",
        ])
        let bytes = try exchange(appURL: appURL, input: input, requestID: requestID)
        return (try decode(bytes, requestID: requestID), bytes)
    }

    static func exchange(appURL: URL, input: Data, requestID: String,
                         onProgress: ((WorkerProgress) -> Void)? = nil) throws -> Data {
        let workerBundle = appURL.appendingPathComponent("Contents/Helpers/CostolaWorker.app")
        let worker = workerBundle.appendingPathComponent("Contents/MacOS/CostolaWorker")
        guard FileManager.default.isExecutableFile(atPath: worker.path) else {
            throw WorkerError.missing
        }
        // Validate the code we are about to launch, including its sealed resources.
        // The launcher is an auxiliary executable, not the enclosing app's main code.
        try verifySignature(workerBundle)
        let process = Process()
        let stdin = Pipe(), stdout = Pipe(), stderr = Pipe()
        process.executableURL = worker
        process.standardInput = stdin
        process.standardOutput = stdout
        process.standardError = stderr
        // The probe has no state or storage access. Do not inherit Python injection variables.
        process.environment = ["PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8"]
        try process.run()
        defer { if process.isRunning { process.terminate() } }
        try stdin.fileHandleForWriting.write(contentsOf: input)
        try stdin.fileHandleForWriting.close()
        // Drain both pipes concurrently; a launch diagnostic must not deadlock stdout.
        let errors = OutputReader(stderr.fileHandleForReading)
        var stream = WorkerStream(requestID: requestID)
        while true {
            let chunk = stdout.fileHandleForReading.availableData
            if chunk.isEmpty { break }
            for progress in try stream.consume(chunk) { onProgress?(progress) }
        }
        process.waitUntilExit()
        let diagnostic = errors.finish()
        if stream.result == nil && !diagnostic.isEmpty {
            throw WorkerError.failed(String(decoding: diagnostic.prefix(4096), as: UTF8.self))
        }
        return try stream.finish(exitCode: process.terminationStatus)
    }

    private static func verifySignature(_ url: URL) throws {
        var code: SecStaticCode?
        let creation = SecStaticCodeCreateWithPath(url as CFURL, [], &code)
        guard creation == errSecSuccess, let code else {
            throw WorkerError.signature(url.lastPathComponent, creation)
        }
        let validity = SecStaticCodeCheckValidity(code, SecCSFlags(rawValue: kSecCSStrictValidate), nil)
        guard validity == errSecSuccess else {
            throw WorkerError.signature(url.lastPathComponent, validity)
        }
    }
}

private final class OutputReader: @unchecked Sendable {
    private let group = DispatchGroup()
    private var data = Data()

    init(_ handle: FileHandle) {
        group.enter()
        DispatchQueue.global().async { [self] in
            while true {
                let chunk = handle.availableData
                if chunk.isEmpty { break }
                if data.count < 4096 { data.append(chunk.prefix(4096 - data.count)) }
            }
            group.leave()
        }
    }

    func finish() -> Data {
        group.wait()
        return data
    }
}
