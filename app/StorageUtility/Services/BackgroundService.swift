import ServiceManagement
import Foundation

@MainActor
enum BackgroundService {
    static var service: SMAppService { .agent(plistName: (Bundle.main.bundleIdentifier ?? "com.cvarisco.costola.dev") + ".agent.plist") }
    static var description: String {
        switch service.status {
        case .enabled: return "macOS allows background checks"
        case .requiresApproval: return "Allow Costola in System Settings → Login Items to run background checks"
        case .notRegistered: return "Background checks are not set up"
        // macOS can report notFound before the first successful registration,
        // even when the bundled helper is present and can be launched.
        case .notFound: return "Background checks are not set up or are unavailable"
        @unknown default: return "macOS could not report the background check status"
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
