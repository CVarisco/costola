import Foundation

struct WorkerProgress: Decodable {
    let phase: String
    let entryId: String
    let operationId: String
}

struct WorkerHeader: Decodable {
    let protocolVersion: Int
    let requestId: String
    let type: String
    let success: Bool?
    let error: WorkerResult.Failure?
}

struct WorkerStream {
    let requestID: String
    private var pending = Data()
    private(set) var result: Data?

    init(requestID: String) { self.requestID = requestID }

    mutating func consume(_ bytes: Data) throws -> [WorkerProgress] {
        pending.append(bytes)
        var progress: [WorkerProgress] = []
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        while let end = pending.firstIndex(of: 10) {
            guard end <= 8 * 1024 * 1024, result == nil else { throw WorkerError.invalidResponse }
            let line = Data(pending[..<end])
            pending.removeSubrange(...end)
            let header = try decoder.decode(WorkerHeader.self, from: line)
            guard header.protocolVersion == 1, header.requestId == requestID else {
                throw WorkerError.invalidResponse
            }
            switch header.type {
            case "progress": progress.append(try decoder.decode(WorkerProgress.self, from: line))
            case "result":
                guard header.success != nil else { throw WorkerError.invalidResponse }
                result = line
            default: throw WorkerError.invalidResponse
            }
        }
        guard pending.count <= 8 * 1024 * 1024 else { throw WorkerError.invalidResponse }
        return progress
    }

    func finish(exitCode: Int32) throws -> Data {
        guard pending.isEmpty, let result else { throw WorkerError.invalidResponse }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let header = try decoder.decode(WorkerHeader.self, from: result)
        guard header.success == true else {
            throw WorkerError.failed(header.error?.message ?? "The operation failed.")
        }
        guard exitCode == 0 else { throw WorkerError.invalidResponse }
        return result
    }
}
