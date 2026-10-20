import XCTest

final class StorageFlowsTests: XCTestCase {
    func testExplicitSelectionPreviewPartialFailureAndRestoreError() {
        let app = XCUIApplication()
        app.launch()
        defer { app.terminate() }
        let review = app.buttons["Review selected folders"]
        XCTAssertTrue(review.waitForExistence(timeout: 10))
        XCTAssertFalse(review.isEnabled)
        app.popUpButtons.firstMatch.click()
        app.typeKey(.downArrow, modifierFlags: [])
        app.typeKey(.return, modifierFlags: [])
        app.buttons["Use this disk"].click()
        XCTAssertTrue(app.staticTexts["SSD storage ready"].waitForExistence(timeout: 5))
        app.scrollViews.containing(.checkBox, identifier: "Select Projects").firstMatch.scroll(byDeltaX: 0, deltaY: -400)
        app.checkBoxes["Select .npm"].click()
        app.checkBoxes["Select Projects"].click()
        XCTAssertTrue(app.staticTexts["2 folders selected"].exists)
        capture(app, name: "Storage selection")
        review.click()
        XCTAssertTrue(app.staticTexts["Before you move these folders"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["You will need the SSD connected to use the SDKs and personal folders you move."].exists)
        capture(app, name: "Migration review")
        app.buttons["Back"].click()
        XCTAssertTrue(app.checkBoxes["Select Projects"].value as? Int == 1)
        review.click()
        XCTAssertFalse(app.staticTexts["Fixture writer is active"].exists)
        app.buttons["Move selected folders"].click()
        XCTAssertTrue(app.staticTexts["Fixture writer is active"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Moved to SSD"].exists)
        XCTAssertTrue(app.buttons["Review folders"].exists)
        capture(app, name: "Individual transfer outcomes")
        app.buttons["Move folders back…"].click()
        app.sheets.buttons["Move folders back"].click()
        XCTAssertTrue(app.staticTexts["Fixture internal storage is full"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["Move folders back…"].isEnabled)
    }

    func testCompactDarkWindowKeepsReviewAccessible() {
        let app = XCUIApplication()
        app.launchArguments = ["-compact", "-dark"]
        app.launch()
        defer { app.terminate() }
        XCTAssertTrue(app.buttons["Review selected folders"].waitForExistence(timeout: 10))
        capture(app, name: "Compact dark setup")
        app.popUpButtons.firstMatch.click()
        app.typeKey(.downArrow, modifierFlags: [])
        app.typeKey(.return, modifierFlags: [])
        app.buttons["Use this disk"].click()
        XCTAssertTrue(app.staticTexts["SSD storage ready"].waitForExistence(timeout: 5))
        app.scrollViews.containing(.checkBox, identifier: "Select Projects").firstMatch.scroll(byDeltaX: 0, deltaY: -400)
        app.checkBoxes["Select Projects"].click()
        let review = app.buttons["Review selected folders"]
        expectation(for: NSPredicate(format: "hittable == true"), evaluatedWith: review)
        waitForExpectations(timeout: 5)
        review.click()
        let move = app.buttons["Move selected folders"]
        XCTAssertTrue(move.waitForExistence(timeout: 5))
        XCTAssertTrue(move.isHittable)
        XCTAssertTrue(app.buttons["Back"].isHittable)
        capture(app, name: "Compact dark migration review")
    }

    private func capture(_ app: XCUIApplication, name: String) {
        let attachment = XCTAttachment(screenshot: app.windows.firstMatch.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
