import re
from playwright.sync_api import Page, expect
from config.config import BASE_URL
from exceptions.booking_exceptions import *
from retries.retry import retry_on_timeout

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

    def shipment_type_dropdown(self):
        # On /book/ship the dropdown button is associated with label "Trip Type"; fallback to visible value.
        return self.page.get_by_label("Trip Type").or_(self.page.get_by_text("Round trip").first)

    def origin_input(self):
        # Locator: placeholder text
        # Why: User-visible placeholder; stable if label changes, better than CSS
        return self.page.get_by_placeholder("Choose origin...")

    def _option_for_address(self, address: str):
        """Option locator that matches address with flexibility (API may return with/without ', USA', etc.)."""
        parts = [p.strip() for p in address.split(",") if p.strip()]
        if len(parts) >= 2:
            # Match street + city so we tolerate format changes
            pattern = re.escape(parts[0]) + r".*" + re.escape(parts[1])
            if len(parts) >= 3:
                # State: accept abbreviation or full name (case-insensitive) for known states
                state_part = parts[2].upper()
                if state_part == "FL":
                    pattern += r".*(?:FL|Florida)"
                elif state_part == "CA":
                    pattern += r".*(?:CA|California)"
                else:
                    pattern += r".*" + re.escape(parts[2])
        else:
            pattern = re.escape(address)
        return self.page.get_by_role("option", name=re.compile(pattern, re.I)).first

    def _wait_for_autocomplete_option(self, address: str):
        """Wait for the address option (div with role='option' in the combobox listbox) to be visible before proceeding.
        We must wait for this element to be visible so the selection is valid and the app does not show
        'Please reselect your address from the drop down list'. Returns the option locator for clicking.
        """
        option = self._option_for_address(address)
        option.wait_for(state="visible")
        return option

    def _fill_and_select_address(self, input_locator, address: str, assert_value_after: bool = True):
        """Fill address, open dropdown (ArrowDown), wait for option, click. Shared by origin/destination."""
        input_locator.fill(address)
        input_locator.press("ArrowDown")
        option = self._wait_for_autocomplete_option(address)
        option.click()
        if assert_value_after:
            expect(input_locator).to_have_value(address)














    def enter_origin(self, address: str):
        def _do():
            self._fill_and_select_address(self.origin_input(), address)
        retry_on_timeout(_do, max_attempts=3, delay_seconds=2.0)

    def click_get_started(self):
        button = self.get_started_button()
        expect(button).to_be_enabled()  # Assertion 2: Enabled state
        button.scroll_into_view_if_needed()  # Handle scroll for lower button
        button.click()
        self.page.wait_for_url("**/book/ship")  # Async handle: Wait for redirect

    def select_shipment_type_one_way(self):
        self.shipment_type_dropdown().click()
        # Options live in HeadlessUI portal; target the option, not the listbox.
        portal = self.page.locator("#headlessui-portal-root")
        one_way_option = portal.get_by_role("option", name=re.compile(r"One[- ]way", re.I)).first
        one_way_option.wait_for(state="visible")
        one_way_option.click()