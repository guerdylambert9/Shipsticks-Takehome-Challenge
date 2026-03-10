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

    def _headlessui_dialog(self):
        """Headless UI renders dialogs in a portal; scope to that so we target the right one."""
        return self.page.locator("#headlessui-portal-root [role='dialog']")

    def origin_input(self):
        # Locator: placeholder text
        # Why: User-visible placeholder; stable if label changes, better than CSS
        return self.page.get_by_placeholder("Choose origin...")

    def destination_input(self):
        # Locator: placeholder text
        # Why: Same as origin – consistent, readable
        return self.page.get_by_placeholder("Choose destination...")

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

    def _dismiss_destination_note_dialog_if_present(self):
        """Dismiss 'Please note before proceeding' modal by clicking I understand.
        Polls until the button appears (async after destination) or max wait — no fixed sleep.
        """
        understand_btn = self.page.get_by_role("button", name=re.compile(r"I understand", re.I)).first
        dialog = self.page.get_by_role("dialog").filter(
            has_text=re.compile(r"Please note", re.I)
        )
        max_wait_ms = 15_000
        poll_ms = 250
        elapsed = 0
        while elapsed < max_wait_ms:
            try:
                if understand_btn.is_visible():
                    understand_btn.click()
                    try:
                        dialog.first.wait_for(state="hidden", timeout=10_000)
                    except Exception:
                        pass
                    return
            except Exception:
                pass
            self.page.wait_for_timeout(poll_ms)
            elapsed += poll_ms

    def _dismiss_cookie_consent_if_present(self):
        """Dismiss OneTrust/cookie banner if visible so it doesn't intercept clicks."""
        accept_btn = self.page.locator("#onetrust-accept-btn-handler").or_(
            self.page.get_by_role("button", name=re.compile(r"Accept all|Accept|Allow all", re.I))
        )
        try:
            accept_btn.first.wait_for(state="visible", timeout=3000)
            accept_btn.first.click()
        except Exception:
            pass

    def _close_any_modal_overlay(self):
        """Close any open modal (e.g. Headless UI dialog) so it doesn't cover the page.
        Tries: 'I understand' click, backdrop click, Escape (multiple), then JS portal clear as last resort.
        """
        dialog = self._headlessui_dialog()
        for attempt in range(3):
            try:
                if not self._is_headlessui_modal_open():
                    return
            except Exception:
                return
            # 1) Click "I understand" if present
            try:
                btn = self.page.get_by_role("button", name="I understand")
                if btn.is_visible():
                    btn.click()
                    dialog.wait_for(state="hidden", timeout=2000)
                    return
            except Exception:
                pass
            # 2) Click Headless UI backdrop
            try:
                portal = self.page.locator("#headlessui-portal-root")
                backdrop = portal.locator("div.fixed[aria-hidden='true']").first
                if backdrop.is_visible():
                    backdrop.click(force=True)
                    dialog.wait_for(state="hidden", timeout=2000)
                    return
            except Exception:
                pass
            # 3) Escape (multiple)
            for _ in range(2):
                self.page.keyboard.press("Escape")
                try:
                    dialog.wait_for(state="hidden", timeout=1500)
                    return
                except Exception:
                    pass
        try:
            dialog.wait_for(state="hidden", timeout=2000)
            return
        except Exception:
            pass
        # 4) Last resort: clear portal and any leftover blocking state on main
        self._dismiss_headlessui_portal_via_js()
        self._ensure_main_content_interactable()
















    def enter_origin(self, address: str):
        def _do():
            self._fill_and_select_address(self.origin_input(), address)
        retry_on_timeout(_do, max_attempts=3, delay_seconds=2.0)

    def enter_destination(self, address: str):
        def _do():
            self._fill_and_select_address(self.destination_input(), address)
            # Single call: polls dynamically until I understand is clickable or timeout
            self._dismiss_destination_note_dialog_if_present()
            self._close_any_modal_overlay()
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

    def select_item_golf_bag_standard(self):
        self._dismiss_destination_note_dialog_if_present()
        self._dismiss_cookie_consent_if_present()
        # Wait for Item Details and scroll so Golf Bags row is in view
        self.page.get_by_text("Golf Bags", exact=True).first.wait_for(state="visible")
        self.page.get_by_text("Golf Bags", exact=True).first.scroll_into_view_if_needed()
        # First input with name productLineCounters.0 is Golf Bags; set value directly (more reliable than + button)
        golf_bags_input = self.page.locator('input[name="productLineCounters.0"]').first
        golf_bags_input.wait_for(state="visible")
        golf_bags_input.scroll_into_view_if_needed()
        golf_bags_input.fill("1")
        expect(golf_bags_input).to_have_value("1")
        