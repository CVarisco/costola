import Foundation

struct Volume: Codable, Identifiable {
    var id: String { uuid }
    let uuid: String
    let mount: String
    let name: String
    let filesystem: String
    let capacity: Int64
}

struct CatalogEntry: Decodable, Identifiable {
    let id: String
    let source: String
    let kind: String
    let offline: String
    let status: String
    let selected: Bool
    let managed: Bool
    let logicalBytes: Int64?
    let allocatedBytes: Int64?
    let reason: String?

    var name: String { URL(fileURLWithPath: source).lastPathComponent }
}

struct ManagedPath: Decodable, Identifiable {
    let id: String
    let source: String
    let kind: String
    let state: String
}

struct StorageOperation: Decodable, Identifiable {
    let id: String
    let entryId: String
    let kind: String
    let phase: String
    let error: String?
}

struct StorageSettings: Codable {
    var cacheBudgetBytes: Int64
    var warningFreePercent: Int
    var urgentFreePercent: Int
}

struct StorageSnapshot: Decodable {
    let revision: Int
    let device: Volume?
    let online: Bool
    let selected: [String]
    let pending: [String]
    let paths: [ManagedPath]
    let settings: StorageSettings
    let operations: [StorageOperation]
    let internalFreeBytes: Int64
    let legacyConflict: Bool
}

struct CatalogResponse: Decodable { let revision: Int; let entries: [CatalogEntry] }
struct VolumeResponse: Decodable { let volumes: [Volume] }
struct MutationResponse: Decodable {
    let revision: Int
    let allSucceeded: Bool?
    let results: [PathResult]?
}
struct PathResult: Decodable { let id: String; let state: String; let error: String? }

struct MigrationPreview: Decodable {
    let revision: Int
    let entries: [CatalogEntry]
    let logicalBytes: Int64
    let estimatedReclaimableBytes: Int64
    let requiredBytes: Int64
    let externalFreeBytes: Int64?
    let preliminary: Bool
    let ready: Bool
    let blockers: [String]
    let note: String
}
