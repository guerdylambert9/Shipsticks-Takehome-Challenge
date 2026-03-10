import re
import time
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
    
    def item_select(self):
        # Locator: role + text
        # Why: Semantic role for select/combo; text for exact match, survives ID changes
        #return self.page.get_by_role("combobox", name="Item")  # Assuming it's a combo; adjust if radio
        return self.page.get_by_label("Golf Bags")

    def delivery_date_picker(self):
        # Staging: button shows "Please select a date" (not "Open calendar"). Try that first, then fallbacks.
        return (
            self.page.get_by_role("button", name="Please select a date")
            .or_(self.page.get_by_role("button", name="Open calendar"))
            .or_(self.page.get_by_role("button", name=re.compile(r"calendar|select date|choose date", re.I)))
        ).first

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

    def _is_headlessui_modal_open(self):
        """Detect if a Headless UI modal is open (dialog or overlay). More reliable than dialog.is_visible() alone."""
        try:
            portal = self.page.locator("#headlessui-portal-root")
            if portal.locator("[data-headlessui-state='open']").first.is_visible():
                return True
            if portal.locator("[role='dialog']").first.is_visible():
                return True
            if portal.locator("div.fixed.inset-0").first.is_visible():
                return True
        except Exception:
            pass
        return False
    
    def _dismiss_headlessui_portal_via_js(self):
        """Last resort: clear Headless UI portal so overlay no longer covers the page."""
        self.page.evaluate("""() => {
            const root = document.getElementById('headlessui-portal-root');
            if (root) root.innerHTML = '';
        }""")

    def _ensure_main_content_interactable(self):
        """Remove inert/aria-hidden from main when modal left the app in a blocked state."""
        self.page.evaluate("""() => {
            document.querySelectorAll('main[inert], main[aria-hidden="true"]').forEach(el => {
                el.removeAttribute('inert');
                el.removeAttribute('aria-hidden');
            });
        }""")

    def _remove_playwright_glass_overlay(self):
        """Remove Playwright-injected x-pw-glass overlay so it doesn't block visibility checks."""
        self.page.evaluate("""() => {
            document.querySelectorAll('x-pw-glass').forEach(el => el.remove());
        }""")

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
            # 1) Click "I understand" if present (case-insensitive; may be <button> or styled link)
            try:
                btn = self.page.get_by_role("button", name=re.compile(r"I understand", re.I)).first
                if btn.is_visible():
                    btn.click(force=True)
                    dialog.wait_for(state="hidden", timeout=5000)
                    return
            except Exception:
                pass
            try:
                btn = self.page.get_by_text(re.compile(r"^\s*I understand\s*$", re.I)).first
                if btn.is_visible():
                    btn.click(force=True)
                    dialog.wait_for(state="hidden", timeout=5000)
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

    def _wait_for_date_picker_visible_while_dismissing_modals(self, timeout_ms: int = 35000):
        """Wait for the delivery date picker to be visible, dismissing any Headless UI modal
        that appears in the meantime. Polls: if a portal modal is open we close it (including
        JS fallback to clear the portal), then re-check for the picker until visible or timeout.
        """
        picker = self.delivery_date_picker()
        deadline = time.time() + (timeout_ms / 1000.0)
        poll_ms = 500
        while time.time() < deadline:
            try:
                if self._is_headlessui_modal_open():
                    self._close_any_modal_overlay()
                    self._remove_playwright_glass_overlay()
                    self._ensure_main_content_interactable()
                    self.page.wait_for_timeout(400)
                    continue
            except Exception:
                pass
            try:
                if picker.is_visible():
                    return
            except Exception:
                pass
            self.page.wait_for_timeout(poll_ms)
        # One more attempt: clear modal, overlays, and any inert/aria-hidden on main
        if self._is_headlessui_modal_open():
            self._dismiss_headlessui_portal_via_js()
            self.page.wait_for_timeout(500)
        self._remove_playwright_glass_overlay()
        self._ensure_main_content_interactable()
        self.page.wait_for_timeout(200)
        picker.wait_for(state="visible", timeout=5000)
















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
        self._close_any_modal_overlay()
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
        # Quantity change can re-open "Please note before proceeding" — close before asserting on radios
        self._dismiss_destination_note_dialog_if_present()
        self._close_any_modal_overlay()
        if self._is_headlessui_modal_open():
            self._dismiss_headlessui_portal_via_js()
        # Validate "Max 42 lb. Standard" is selected by default for Golf Bags #1
        standard_option = self.page.get_by_role("radio", name=re.compile(r"Max 42 lb\.\s*Standard|Standard", re.I))
        expect(standard_option.first).to_be_checked()

    def select_delivery_date(self, date_str: str):
        self._dismiss_destination_note_dialog_if_present()
        self._dismiss_cookie_consent_if_present()
        self._close_any_modal_overlay()
        # Wait for Headless UI portal dialog to be gone so the date picker isn't covered
        try:
            self._headlessui_dialog().wait_for(state="hidden", timeout=5000)
        except Exception:
            pass
        self.page.get_by_text(re.compile(r"delivery|date|when", re.I)).first.scroll_into_view_if_needed()
        self._wait_for_date_picker_visible_while_dismissing_modals()
        picker = self.delivery_date_picker()
        picker.scroll_into_view_if_needed()
        picker.click()
        self.page.wait_for_selector("[role='grid']")
        # Parse "April 8, 2026" -> month name and day number; calendar opens on current month (e.g. March 2026)
        month_match = re.search(r"(\w+)\s+\d{1,2}", date_str)
        month_name = month_match.group(1) if month_match else ""
        day_match = re.search(r"\b(\d{1,2})\b", date_str)
        day_num = day_match.group(1) if day_match else date_str
        # Navigate to the correct month: click next-month until calendar shows e.g. "April 2026"
        # Staging uses icon-only button (icon-arrow-right); aria-label fallback for other envs
        next_btn = self.page.locator("button").filter(has=self.page.locator(".icon-arrow-right")).first.or_(
            self.page.get_by_role("button", name=re.compile(r"next month|go to next", re.I))
        )
        target_header = re.compile(rf"{month_name}\s+\d{{4}}", re.I)
        for _ in range(12):
            if self.page.get_by_text(target_header).first.is_visible():
                break
            try:
                next_btn.click(timeout=3000)
                self.page.wait_for_timeout(300)
            except Exception:
                break
        # Click the enabled day only (avoid disabled days like past dates or from other months)
        day_cell = self.page.locator("button.rdp-day:not(.rdp-day_disabled)").filter(has_text=re.compile(rf"^{day_num}$"))
        day_cell.first.click()
        # After selection the trigger no longer says "Please select a date" (it shows e.g. "Apr 8, 2026");
        # assert the selected date appears on the page (e.g. in main / shipment dates section).
        date_displayed = re.compile(r"Apr(il)?\s*\d{1,2},?\s*2026|2026", re.I)
        expect(self.page.locator("main")).to_contain_text(date_displayed)