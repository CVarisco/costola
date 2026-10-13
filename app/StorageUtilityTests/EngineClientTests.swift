import XCTest
@testable import Costola

final class EngineClientTests: XCTestCase {
    let result = #"{"protocol_version":1,"request_id":"fixture","type":"result","success":true,"data":{}}"# + "\n"

    func testFragmentedUnicodeLinesProduceOneResult() throws {
        var stream = WorkerStream(requestID: "fixture")
        let bytes = Data((#"{"protocol_version":1,"request_id":"fixture","type":"progress","phase":"copia","entry_id":"caffè","operation_id":"op"}"# + "\n" + result).utf8)
        var progress: [WorkerProgress] = []
        for byte in bytes { progress += try stream.consume(Data([byte])) }
        XCTAssertEqual(progress.first?.entryId, "caffè")
        XCTAssertEqual(progress.count, 1)
        XCTAssertNoThrow(try stream.finish(exitCode: 0))
    }

    func testEOFAndZeroExitWithoutResultAreNotSuccess() {
        let stream = WorkerStream(requestID: "fixture")
        XCTAssertThrowsError(try stream.finish(exitCode: 0))
    }

    func testNonzeroExitAndTruncatedResultAreNotSuccess() throws {
        var complete = WorkerStream(requestID: "fixture")
        _ = try complete.consume(Data(result.utf8))
        XCTAssertThrowsError(try complete.finish(exitCode: 1))
        var truncated = WorkerStream(requestID: "fixture")
        _ = try truncated.consume(Data(result.dropLast().utf8))
        XCTAssertThrowsError(try truncated.finish(exitCode: 0))
    }

    func testRepeatedFinalResultIsRejected() throws {
        var stream = WorkerStream(requestID: "fixture")
        _ = try stream.consume(Data(result.utf8))
        XCTAssertThrowsError(try stream.consume(Data(result.utf8)))
    }

    func testSharedPythonFixtureDecodesIntoSnapshot() throws {
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "events", withExtension: "json", subdirectory: "protocol"))
        let events = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [[String: Any]])
        var stream = WorkerStream(requestID: "fixture")
        for event in events {
            var line = try JSONSerialization.data(withJSONObject: event)
            line.append(10)
            _ = try stream.consume(line)
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let snapshot = try decoder.decode(EnginePayload<StorageSnapshot>.self, from: stream.finish(exitCode: 0)).data
        XCTAssertEqual(snapshot.revision, 0)
        XCTAssertTrue(snapshot.selected.isEmpty)
        XCTAssertNil(snapshot.device)
    }
}
