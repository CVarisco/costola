import Foundation

struct EnginePayload<Value: Decodable>: Decodable { let data: Value }

protocol EngineServing: Sendable {
    func request<Value: Decodable>(_ command: String, arguments: [String: Any],
                                    onProgress: ((WorkerProgress) -> Void)?) async throws -> Value
}

final class EngineClient: EngineServing, @unchecked Sendable {
    let appURL: URL

    init(appURL: URL = Bundle.main.bundleURL) { self.appURL = appURL }

    func request<Value: Decodable>(_ command: String, arguments: [String: Any] = [:],
                                    onProgress: ((WorkerProgress) -> Void)? = nil) async throws -> Value {
        let requestID = UUID().uuidString
        let input = try JSONSerialization.data(withJSONObject: [
            "protocol_version": 1, "request_id": requestID,
            "operation_id": requestID, "command": command, "arguments": arguments,
        ])
        let appURL = self.appURL
        return try await Task.detached {
            let data = try BundleWorker.exchange(appURL: appURL, input: input,
                                                requestID: requestID, onProgress: onProgress)
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            return try decoder.decode(EnginePayload<Value>.self, from: data).data
        }.value
    }
}
