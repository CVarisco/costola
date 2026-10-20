import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var model: StorageModel
    @State private var budget = 5.0
    @State private var warning = 10
    @State private var urgent = 5

    private var validBudget: Bool {
        budget.isFinite && budget >= 0 && budget * 1_073_741_824 < Double(Int64.max)
    }

    var body: some View {
        Form {
            Section("Background automation") {
                Text(model.serviceStatus)
                Text("Checks the folders you moved every minute and cleans eligible caches every 15 minutes, even with the window closed.").font(.callout).foregroundStyle(.secondary)
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
                    if background.result.lowSpace == true { Text("Your Mac has less free space than the warning level you set.").foregroundStyle(.orange) }
                    if background.result.overBudget == true { Text("Caches are over your limit. Close tools using them so Costola can clean up.").foregroundStyle(.orange) }
                }
            }
            Section("Cache space on this Mac") {
                TextField("Cache limit (GiB)", value: $budget, format: .number)
                Text("Costola cleans only supported caches that are not in use. It keeps your personal folders and SDKs. Active tools can temporarily exceed this limit.").font(.callout).foregroundStyle(.secondary)
            }
            Section("Free space on this Mac") {
                Stepper("Warn below \(warning)% free", value: $warning, in: 1...100)
                Stepper("Urgent cleanup below \(urgent)% free", value: $urgent, in: 0...99)
                Text("Active tools are never stopped to force cleanup.").font(.callout).foregroundStyle(.secondary)
            }
            Button("Save settings") { Task { await model.saveSettings(budgetGiB: budget, warning: warning, urgent: urgent) } }
                .disabled(model.isBusy || model.snapshot == nil || !validBudget || urgent >= warning)
            if !validBudget {
                Label("Enter a cache limit of zero or more within the supported size range.", systemImage: "exclamationmark.circle")
                    .font(.callout).foregroundStyle(.orange)
            }
            if urgent >= warning {
                Label("Set urgent cleanup below the warning percentage so you get a warning first.", systemImage: "exclamationmark.circle")
                    .font(.callout).foregroundStyle(.orange)
            }
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
