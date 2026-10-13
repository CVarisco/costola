import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var model: StorageModel
    @State private var budget = 5.0
    @State private var warning = 10
    @State private var urgent = 5

    var body: some View {
        Form {
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
                Text("Costola · Development build")
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
