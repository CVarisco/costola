import XCTest
@testable import Costola

final class BundleLaunchTests: XCTestCase {
    func testIncompleteResponseIsNotSuccess() {
        XCTAssertThrowsError(try BundleWorker.decode(Data("{}".utf8), requestID: "probe"))
    }

    func testIncompatibleProtocolIsNotSuccess() {
        let data = Data(#"{"protocol_version":2,"request_id":"probe","type":"result","success":true,"data":{"product":"Costola","capabilities":["info"],"python_version":"3.14.6","architecture":"arm64","frozen":true}}"#.utf8)
        XCTAssertThrowsError(try BundleWorker.decode(data, requestID: "probe"))
    }

    func testMatchingFrozenWorkerResponseIsAccepted() throws {
        let data = Data(#"{"protocol_version":1,"request_id":"probe","type":"result","success":true,"data":{"product":"Costola","capabilities":["info"],"python_version":"3.14.6","architecture":"arm64","frozen":true}}"#.utf8)
        XCTAssertEqual(try BundleWorker.decode(data, requestID: "probe").data?.product, "Costola")
        XCTAssertThrowsError(try BundleWorker.decode(data, requestID: "different"))
    }

    func testMissingWorkerIsReported() {
        XCTAssertThrowsError(try BundleWorker.probe(appURL: URL(fileURLWithPath: "/nonexistent/Costola.app")))
    }
}
