// Compiled only into the temporary service-test app, never into Costola.
import Foundation
import ServiceManagement

let service = SMAppService.agent(plistName: "costola-test.plist")
do {
    try service.register()
    defer {
        do { try service.unregister() }
        catch { fputs("unregister failed: \(error)\n", stderr) }
    }
    guard service.status == .enabled else {
        throw NSError(domain: "CostolaServiceTest", code: 1, userInfo: [
            NSLocalizedDescriptionKey: "Service needs system approval (status \(service.status.rawValue)); automatic launch is not verified.",
        ])
    }
    let output = URL(fileURLWithPath: CommandLine.arguments[1])
    let deadline = Date().addingTimeInterval(15)
    var succeeded = false
    while Date() < deadline {
        if let data = try? Data(contentsOf: output),
           let response = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           response["success"] as? Bool == true {
            print("Service launched the bundled worker successfully.")
            succeeded = true
            break
        }
        Thread.sleep(forTimeInterval: 0.2)
    }
    if !succeeded {
        throw NSError(domain: "CostolaServiceTest", code: 2, userInfo: [
            NSLocalizedDescriptionKey: "Registered service did not produce a successful worker result.",
        ])
    }
} catch {
    // Unregister explicitly here too: failed registration may leave a pending item.
    try? service.unregister()
    fputs("\(error.localizedDescription)\n", stderr)
    exit(1)
}
