import ServiceManagement
import Foundation

@MainActor
enum BackgroundService {
    static var service: SMAppService { .agent(plistName: (Bundle.main.bundleIdentifier ?? "com.cvarisco.costola.dev") + ".agent.plist") }
    static var description: String {
        switch service.status {
        case .enabled: return "Allowed by macOS"
        case .requiresApproval: return "Approval needed in System Settings → Login Items"
        case .notRegistered: return "Not registered"
        // macOS can report notFound before the first successful registration,
        // even when the bundled helper is present and can be launched.
        case .notFound: return "Not registered or unavailable"
        @unknown default: return "Unknown service status"
        }
    }
    static func enable() throws {
        if service.status != .enabled { try service.register() }
    }
    static func disable() async throws {
        if service.status != .notRegistered { try await service.unregister() }
    }
    static func openSettings() { SMAppService.openSystemSettingsLoginItems() }
}
