import re
from playwright.sync_api import Page, expect
from config.config import BASE_URL
from exceptions.booking_exceptions import *

class BookingStep1Page:
    def __init__(self, page: Page):
        self.page = page
        self.url = f"{BASE_URL}/book/ship"  # Direct to booking (after Get Started click); no full hardcoded URLs

    def navigate_to_landing(self) -> None:
        """Open the staging landing page."""
        self.page.goto(BASE_URL)
        # Staging title; prod may differ (e.g. "ShipSticks: Ship Golf Clubs Door-to-Door")
        expect(self.page).to_have_title(re.compile(r"Ship.*Golf|Golf.*Ship", re.I))

    def get_started_button(self):
        # Staging: header has disabled "Get started" (button); main section has enabled CTA (often <a>).
        # Scroll to main section first so the enabled CTA is in view/DOM, then match both button and link.
        self.page.get_by_text("Great golf trips", exact=False).first.scroll_into_view_if_needed()
        return self.page.locator("a, button").filter(has_text=re.compile(r"Get started", re.I)).nth(1)

    # def click_get_started(self) -> None:
    #     """Click Get Started to go to booking step 1."""
    #     self.page.get_by_role("link", name="Get Started").click()

    def click_get_started(self):
        button = self.get_started_button()
        expect(button).to_be_enabled()  # Assertion 2: Enabled state
        button.scroll_into_view_if_needed()  # Handle scroll for lower button
        button.click()
        self.page.wait_for_url("**/book/ship")  # Async handle: Wait for redirect