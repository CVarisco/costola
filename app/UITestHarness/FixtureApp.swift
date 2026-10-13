// A separate test-only app target. Never included in Costola's release bundle.
import SwiftUI

@main
struct FixtureApp: App {
    @StateObject private var model = StorageModel(client: FixtureEngine())
    var body: some Scene {
        Window("Costola fixture", id: "storage") {
            CostolaRootView().environmentObject(model).frame(minWidth: 820, minHeight: 570)
        }.defaultSize(width: 1040, height: 720)
    }
}

private actor FixtureEngine: EngineServing {
    var chosen = false
    var migrated = false
    let volume: [String: Any] = ["uuid": "fixture", "mount": "/Fixture/SSD", "name": "Fixture SSD", "filesystem": "apfs", "capacity": 100_000_000_000]
    var entries: [[String: Any]] {
        [["id": "npm", "source": "/Fixture/.npm", "kind": "cache", "offline": "local-cache", "status": "available", "selected": migrated, "managed": migrated, "allocated_bytes": 1000],
         ["id": "personal", "source": "/Fixture/Projects", "kind": "persistent", "offline": "requires-disk", "status": "available", "selected": false, "managed": false, "allocated_bytes": 2000]]
    }
    func request<Value: Decodable>(_ command: String, arguments: [String: Any],
                                   onProgress: ((WorkerProgress) -> Void)?) async throws -> Value {
        let result: [String: Any]
        switch command {
        case "status":
            var state: [String: Any] = ["revision": 1, "online": chosen, "selected": migrated ? ["npm"] : [], "pending": [],
                "paths": migrated ? [["id": "npm", "source": "/Fixture/.npm", "kind": "cache", "state": "external"]] : [],
                "operations": [], "internal_free_bytes": 10_000_000_000, "legacy_conflict": false,
                "settings": ["cache_budget_bytes": 5_368_709_120, "warning_free_percent": 10, "urgent_free_percent": 5]]
            if chosen { state["device"] = volume }
            result = state
        case "discover": result = ["revision": 1, "entries": entries]
        case "volumes": result = ["volumes": [volume]]
        case "choose_device": chosen = true; result = ["revision": 1]
        case "preview":
            let ids = arguments["ids"] as? [String] ?? []
            result = ["revision": 1, "entries": entries.filter { ids.contains($0["id"] as? String ?? "") },
                      "logical_bytes": 3000, "estimated_reclaimable_bytes": 3000, "required_bytes": 1_073_744_824,
                      "preliminary": false, "ready": true, "blockers": [], "note": "Fixture estimate"]
        case "migrate":
            migrated = true
            result = ["revision": 1, "all_succeeded": false, "results": [
                ["id": "npm", "state": "external"], ["id": "personal", "state": "blocked", "error": "Fixture writer is active"]]]
        case "restore":
            result = ["revision": 1, "all_succeeded": false,
                      "results": [["id": "npm", "state": "blocked", "error": "Fixture internal storage is full"]]]
        default: throw NSError(domain: "Fixture", code: 1, userInfo: [NSLocalizedDescriptionKey: "Unexpected fixture action"])
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(Value.self, from: JSONSerialization.data(withJSONObject: result))
    }
}
