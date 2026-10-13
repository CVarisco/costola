import Foundation
import UserNotifications

enum Notifications {
    static func authorize() async throws -> Bool {
        try await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound])
    }

    static func sendStorageAttention() async throws {
        let center = UNUserNotificationCenter.current()
        let settings = await center.notificationSettings()
        guard settings.authorizationStatus == .authorized else { return }
        let content = UNMutableNotificationContent()
        content.title = "Costola needs attention"
        content.body = "Open Costola to check storage, cache limits or an interrupted transfer."
        try await center.add(UNNotificationRequest(identifier: "storage-attention", content: content, trigger: nil))
    }
}
