import XCTest

final class StorageFlowsTests: XCTestCase {
    func testExplicitSelectionPreviewPartialFailureAndRestoreError() {
        let app = XCUIApplication()
        app.launch()
        defer { app.terminate() }
        let review = app.buttons["Review migration"]
        XCTAssertTrue(review.waitForExistence(timeout: 10))
        XCTAssertFalse(review.isEnabled)
        app.popUpButtons.firstMatch.click()
        app.typeKey(.downArrow, modifierFlags: [])
        app.typeKey(.return, modifierFlags: [])
        app.buttons["Use this disk"].click()
        XCTAssertTrue(app.staticTexts["Storage available"].waitForExistence(timeout: 5))
        app.checkBoxes["Select .npm"].click()
        app.checkBoxes["Select Projects"].click()
        review.click()
        XCTAssertTrue(app.staticTexts["Review your migration"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.staticTexts["Fixture writer is active"].exists)
        app.buttons["Move selected folders"].click()
        XCTAssertTrue(app.staticTexts["Fixture writer is active"].waitForExistence(timeout: 5))
        app.buttons["Restore managed folders…"].click()
        app.sheets.buttons["Restore folders"].click()
        XCTAssertTrue(app.staticTexts["Fixture internal storage is full"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["Restore managed folders…"].isEnabled)
    }
}
