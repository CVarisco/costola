import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var model: StorageModel
    @State private var budget = 5.0
    @State private var warning = 10
    @State private var urgent = 5

    var body: some View {
        Form {
            Section("Background automation") {
                Text(model.serviceStatus)
                Text("Checks authorized folders every minute and the cache budget every 15 minutes, including when the window is closed.").font(.callout).foregroundStyle(.secondary)
                HStack {
                    Button(model.snapshot?.automationEnabled == true ? "Disable automation" : "Enable automation") {
                        Task { await model.setAutomation(model.snapshot?.automationEnabled != true) }
                    }.disabled(model.isBusy || (model.snapshot?.paths.isEmpty != false && model.snapshot?.automationEnabled != true))
                    Button("System Settings…") { BackgroundService.openSettings() }
                }
                Button("Allow storage notifications…") { Task { await model.enableNotifications() } }
                if let background = model.snapshot?.background {
                    Text("Last check: \(Date(timeIntervalSince1970: background.checkedAt).formatted()) · \(background.result.state)").font(.caption)
                    ForEach(background.result.errors ?? [], id: \.self) { Text($0).foregroundStyle(.orange) }
                    if background.result.lowSpace == true { Text("Internal free space is below your warning threshold.").foregroundStyle(.orange) }
                    if background.result.overBudget == true { Text("Cache budget exceeded. Close active tools to allow cleanup.").foregroundStyle(.orange) }
                }
            }
            Section("Local cache budget") {
                TextField("Budget (GiB)", value: $budget, format: .number)
                Text("Only recognized, inactive caches can be cleaned. Personal folders and SDKs are always preserved.").font(.callout).foregroundStyle(.secondary)
            }
            Section("Internal free space") {
                Stepper("Warn below \(warning)% free", value: $warning, in: 1...100)
                Stepper("Urgent cleanup below \(urgent)% free", value: $urgent, in: 0...99)
                Text("Active tools are never stopped to force cleanup.").font(.callout).foregroundStyle(.secondary)
            }
            Button("Save settings") { Task { await model.saveSettings(budgetGiB: budget, warning: warning, urgent: urgent) } }
                .disabled(model.isBusy || urgent >= warning)
            Section("About") {
                Text("Costola \(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "")")
                Link("Source and releases on GitHub", destination: URL(string: "https://github.com/CVarisco/costola")!)
            }
        }.formStyle(.grouped).navigationTitle("Settings")
            .onAppear {
                if let settings = model.snapshot?.settings {
                    budget = Double(settings.cacheBudgetBytes) / 1_073_741_824
                    warning = settings.warningFreePercent
                    urgent = settings.urgentFreePercent
                }
            }
    }
}
