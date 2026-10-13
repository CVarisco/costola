import XCTest
@testable import Costola

private actor FixtureEngine: EngineServing {
    var commands: [String] = []
    var partialFailure = false
    let entry: [String: Any] = ["id": "npm", "source": "/fixture/.npm", "kind": "cache", "offline": "local-cache", "status": "available", "selected": false, "managed": false]

    func failOneFolder() { partialFailure = true }

    func request<Value: Decodable>(_ command: String, arguments: [String: Any],
                                   onProgress: ((WorkerProgress) -> Void)?) async throws -> Value {
        commands.append(command)
        let response: [String: Any]
        switch command {
        case "status":
            response = ["revision": 4, "online": false, "selected": [], "pending": [], "paths": [],
                        "settings": ["cache_budget_bytes": 5_368_709_120, "warning_free_percent": 10, "urgent_free_percent": 5],
                        "operations": [], "internal_free_bytes": 1_000_000, "legacy_conflict": false]
        case "discover": response = ["revision": 4, "entries": [entry]]
        case "volumes": response = ["volumes": []]
        case "preview":
            response = ["revision": 4, "entries": [entry], "logical_bytes": 10, "estimated_reclaimable_bytes": 10,
                        "required_bytes": 20, "preliminary": true, "ready": true, "blockers": [], "note": "Estimate"]
        case "migrate":
            XCTAssertEqual(arguments["ids"] as? [String], ["npm"])
            XCTAssertEqual(arguments["revision"] as? Int, 4)
            response = ["revision": 5, "all_succeeded": !partialFailure,
                        "results": [["id": "npm", "state": partialFailure ? "blocked" : "external", "error": "Writer active"]]]
        default: throw NSError(domain: "Unexpected command", code: 1)
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(Value.self, from: JSONSerialization.data(withJSONObject: response))
    }
}

@MainActor
final class StorageModelTests: XCTestCase {
    func testDiscoveryDoesNotAuthorizeFoldersOrStartMigration() async {
        let client = FixtureEngine()
        let model = StorageModel(client: client)
        await model.refresh()
        XCTAssertEqual(model.visibleEntries.count, 1)
        XCTAssertTrue(model.selection.isEmpty)
        let commands = await client.commands
        XCTAssertEqual(Set(commands), ["status", "discover", "volumes"])
    }

    func testPreviewRequiresSeparateConfirmationAndUsesReviewedSelection() async {
        let client = FixtureEngine()
        let model = StorageModel(client: client)
        await model.refresh()
        model.selection = ["npm"]
        await model.showPreview()
        var commands = await client.commands
        XCTAssertFalse(commands.contains("migrate"))
        XCTAssertNotNil(model.preview)
        model.selection = []
        await model.confirmMigration()
        commands = await client.commands
        XCTAssertEqual(commands.filter { $0 == "migrate" }.count, 1)
        XCTAssertNil(model.preview)
        XCTAssertFalse(model.isMutating)
    }

    func testPartialFailureRemainsVisibleWithIndividualResult() async {
        let client = FixtureEngine()
        await client.failOneFolder()
        let model = StorageModel(client: client)
        await model.refresh()
        model.selection = ["npm"]
        await model.showPreview()
        await model.confirmMigration()
        XCTAssertEqual(model.section, .operations)
        XCTAssertEqual(model.results.first?.state, "blocked")
        XCTAssertNotNil(model.error)
        XCTAssertFalse(model.isBusy)
    }
}
