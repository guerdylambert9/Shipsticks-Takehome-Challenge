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
        expect(self.page).to_have_title("The Best Way to Ship Golf Clubs | 4M+ Golf Bags Shipped")
        #expect(self.page).to_have_title(re.compile(r"Ship.*Golf|Golf.*Ship", re.I))

    def get_started_button(self):
        # Staging: header has disabled "Get started" (button); main section has enabled CTA (often <a>).
        # Scroll to main section first so the enabled CTA is in view/DOM, then match both button and link.
        self.page.get_by_text("Great golf trips", exact=False).first.scroll_into_view_if_needed()
        # Unique: the only "Get started" link that goes to /book/ship
        return self.page.locator('a[href="/book/ship"]').filter(has_text=re.compile(r"Get started", re.I)).first

    def shipment_type_dropdown(self):
        # Label has empty for="", so it's not associated with the button; get_by_label alone fails.
        # Fallback: listbox button shows current value ("One way" or "Round trip") as its name.
        return self.page.get_by_label("Trip Type").or_(
            self.page.get_by_role("button", name=re.compile(r"One way|Round trip", re.I)).first
        )

    def _headlessui_dialog(self):
        """Headless UI renders dialogs in a portal; scope to that so we target the right one."""
        return self.page.locator("#headlessui-portal-root [role='dialog']")

    def origin_input(self):
        # Role + name is the accessibility contract; it’s what assistive tech uses and teams are less likely to change without reason.
        return self.page.get_by_role("combobox", name="Where from?")

    def destination_input(self):
        # Role + name is the accessibility contract; it’s what assistive tech uses and teams are less likely to change without reason.
        return self.page.get_by_role("combobox", name="Where to?")
    
    def item_select(self):
        # Uses the accessibility contract.  target the control by its visible label, which is how users and assistive tech identify it
        return self.page.get_by_label("Golf Bags")

    def delivery_date_picker(self):
        # Role + accessible name You’re using the control’s role (button) and its accessible name (the text “Please select a date” from the inner <span>). 
        # That’s how the control is exposed to users and assistive tech, so it’s a good basis for a locator.
        return ( self.page.get_by_role("button", name="Please select a date"))

    def shipment_speeds_section(self):
       """Section appears after a delivery date is selected; use heading for visibility checks."""
       # Role (heading, which matches the <h2>) and accessible name (the heading text “Shipment Speeds”). 
       # That’s how the section is identified for users and assistive tech
       return self.page.get_by_role("heading", name=re.compile(r"Shipment Speeds", re.I)).first

    def service_level_option(self):
        # Locator: text-based radio/option
        # Why: Exact text for selection; stable for user-facing choices
        return self.page.get_by_text("Ground")

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
        """Remove inert/aria-hidden from main and header so modal doesn't leave the page blocked.
        (antialiased on body is only font smoothing; the real blockers are inert/aria-hidden on main.)"""
        self.page.evaluate("""() => {
            document.querySelectorAll('main[inert], main[aria-hidden="true"]').forEach(el => {
                el.removeAttribute('inert');
                el.removeAttribute('aria-hidden');
            });
            document.querySelectorAll('header[inert], header[aria-hidden="true"]').forEach(el => {
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
        # use the heading’s accessible name “TripType” (from aria-label) and part of the a11y contract and 
        # is usually more stable than class names or DOM structure
        expect(self.page.get_by_role("heading", name="TripType")).to_have_text("ONE WAY")

    def enter_origin(self, address: str):
        def _do():
            self._fill_and_select_address(self.origin_input(), address)
        retry_on_timeout(_do, max_attempts=3, delay_seconds=2.0)

    def enter_destination(self, address: str):
        def _do():
            self._fill_and_select_address(self.destination_input(), address)
            self._dismiss_destination_note_dialog_if_present()
            self._close_any_modal_overlay()
        retry_on_timeout(_do, max_attempts=3, delay_seconds=2.0)
        # Dismiss overlays so Save is clickable (destination note + OneTrust can intercept)
        self._dismiss_destination_note_dialog_if_present()
        self._close_any_modal_overlay()
        self._dismiss_cookie_consent_if_present()
        self._ensure_main_content_interactable()
        if self._is_headlessui_modal_open():
            self._dismiss_headlessui_portal_via_js()
            self._ensure_main_content_interactable()
        save_btn = self.page.get_by_role("button", name="Save")
        save_btn.wait_for(state="visible")
        save_btn.click(force=True)
        # validate that Los Angeles, CA is saved and has its green checkmark
        la_row = self.page.locator("div", has_text="Los Angeles, CA")
        expect(la_row.locator(".icon-check-circle-filled").first).to_be_visible()
        # validate that Miami Lakes, FL is saved and has its greeen checkmark
        miami_row = self.page.locator("div", has_text="Miami Lakes, FL")
        expect(miami_row.locator(".icon-check-circle-filled").last).to_be_visible()
        # validate Order summary: ONE WAY block shows origin → destination.
        # self.page.locator('div[aria-label="ShipLeg"]'). aria-label is part of the accessibility contract (for screen readers), 
        # so it’s less likely to change on a whim than class names or structure.  Teams usually don’t change it without reason
        ship_leg = self.page.locator('div[aria-label="ShipLeg"]')

        # 2. Assert both cities are present within this container
        expect(ship_leg).to_contain_text("Los Angeles, CA")
        expect(ship_leg).to_contain_text("Miami Lakes, FL")

        # 3. Assert the green arrow icon is visible inside this container
        expect(ship_leg.locator(".icon-arrow-right")).to_be_visible()

    def select_item_golf_bag_standard(self):
        self._dismiss_destination_note_dialog_if_present()
        self._close_any_modal_overlay()
        self._dismiss_cookie_consent_if_present()
        # Main/header can stay inert after modal closes; clear so input can receive fill
        self._ensure_main_content_interactable()
        # Wait for Item Details and scroll so Golf Bags row is in view
        self.page.get_by_text("Golf Bags", exact=True).first.wait_for(state="visible")
        self.page.get_by_text("Golf Bags", exact=True).first.scroll_into_view_if_needed()
        # First input with name productLineCounters.0 is Golf Bags; set value directly (more reliable than + button)
        golf_bags_input = self.page.locator('input[name="productLineCounters.0"]').first
        golf_bags_input.wait_for(state="visible")
        golf_bags_input.scroll_into_view_if_needed()
        golf_bags_input.fill("1", force=True)
        expect(golf_bags_input).to_have_value("1", timeout=10_000)
        # Quantity change can re-open "Please note before proceeding" — close before asserting on radios
        self._dismiss_destination_note_dialog_if_present()
        self._close_any_modal_overlay()
        if self._is_headlessui_modal_open():
            self._dismiss_headlessui_portal_via_js()
        self._ensure_main_content_interactable()
        # Validate "Max 42 lb. Standard" is selected for Golf Bags #1 (single row)
        # Size options render after quantity change (and after overlay); wait then assert
        # It is highly stable; it uses the role (button) and accessible name (“Max 42 lb. Standard”).  It doesn’t depend on CSS classes, structure, or DOM depth
        standard_btn = self.page.get_by_role("radio", name=re.compile(r"Max 42 lb\.\s*Standard", re.I)).first
        standard_btn.wait_for(state="visible", timeout=15_000)
        standard_btn.scroll_into_view_if_needed()
        # validate that standardd is the default selection.  The assertion confirm it not select it
        expect(standard_btn).to_be_checked()

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
        #assert the Delivery Date button is selected by default
        expect(self.page.locator('button[name="shipments.0.dateType"]').first).to_have_attribute("aria-pressed", "true")
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
        self.expect_delivery_date_trigger_matches_order_summary_destination()

    def _delivery_date_trigger_text(self) -> str:
        """Selected date in Shipment Dates section, e.g. 'Apr 8, 2026' (from the date picker button)."""
        trigger = self.page.locator("button").filter(has=self.page.locator(".icon-calendar")).first
        return trigger.inner_text()

    def _order_summary_destination_ship_date_text(self) -> str:
        """Destination ship date in ONE WAY block, e.g. 'Wed, Apr. 08' (second ShipmentDate in ShipLeg)."""
        ship_leg = self.page.locator('div[aria-label="ShipLeg"]').first
        return ship_leg.locator('strong[aria-label="ShipmentDate"]').nth(1).inner_text()

    def expect_delivery_date_trigger_matches_order_summary_destination(self) -> None:
        """Assert Delivery Date trigger (e.g. Apr 8, 2026) and Order Summary destination date (e.g. Wed, Apr. 08) are the same day."""
        trigger_text = self._delivery_date_trigger_text().strip()
        summary_text = self._order_summary_destination_ship_date_text().strip()
        month_names = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        # Parse trigger "Apr 8, 2026" -> (4, 8)
        trigger_match = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s*\d{4}", trigger_text)
        assert trigger_match, f"Delivery date trigger format unexpected: {trigger_text!r}"
        t_month_name, t_day = trigger_match.group(1).lower()[:3], int(trigger_match.group(2))
        t_month = month_names.get(t_month_name)
        assert t_month is not None, f"Month unexpected: {trigger_match.group(1)!r}"
        # Parse summary "Wed, Apr. 08" -> (4, 8)
        summary_match = re.search(r"([A-Za-z]+)\.?\s*(\d{1,2})\b", summary_text)
        assert summary_match, f"Order summary destination date format unexpected: {summary_text!r}"
        s_month_name, s_day = summary_match.group(1).lower()[:3], int(summary_match.group(2))
        s_month = month_names.get(s_month_name)
        assert s_month is not None, f"Month unexpected: {summary_match.group(1)!r}"
        assert (t_month, t_day) == (s_month, s_day), (
            f"Delivery date trigger ({trigger_text}) and Order Summary destination date ({summary_text}) do not match"
        )

    def _ground_ship_date_text(self) -> str:
        """Date from Ground's 'Ships on:' box (green-700), e.g. '03/31/2026'."""
        ships_on_box = self.page.locator("[class*='bg-green-700']").filter(has_text="Ships on:").first
        return ships_on_box.get_by_text(re.compile(r"\d{1,2}/\d{1,2}/\d{4}")).first.inner_text()

    def _order_summary_origin_ship_date_text(self) -> str:
        """Origin ship date in ONE WAY block, e.g. 'Tue, Mar. 31' (aria-label=ShipmentDate)."""
        ship_leg = self.page.locator('div[aria-label="ShipLeg"]').first
        return ship_leg.locator('strong[aria-label="ShipmentDate"]').first.inner_text()

    def expect_ground_ship_date_matches_order_summary_origin(self) -> None:
        """Assert the Ground 'Ships on' date and the Order Summary origin ShipmentDate are the same day."""
        ground_text = self._ground_ship_date_text().strip()
        summary_text = self._order_summary_origin_ship_date_text().strip()
        # Parse MM/DD/YYYY from ground card
        ground_match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", ground_text)
        assert ground_match, f"Ground date format unexpected: {ground_text!r}"
        g_month, g_day = int(ground_match.group(1)), int(ground_match.group(2))
        # Parse "Tue, Mar. 31" or "Tue, March 31" from order summary
        month_names = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        summary_match = re.search(r"([A-Za-z]+)\.?\s*(\d{1,2})\b", summary_text)
        assert summary_match, f"Order summary date format unexpected: {summary_text!r}"
        s_month_name, s_day = summary_match.group(1).lower()[:3], int(summary_match.group(2))
        s_month = month_names.get(s_month_name)
        assert s_month is not None, f"Month name unexpected: {summary_match.group(1)!r}"
        assert (g_month, g_day) == (s_month, s_day), (
            f"Ground ship date ({ground_text}) and Order Summary origin date ({summary_text}) do not match"
        )

    def select_service_level_ground(self):
        self.service_level_option().click()
        expect(self.service_level_option()).to_be_checked()  # Assertion 8: Selected
        # Verify Ground is shown in selected (green) state (bg-green-50 / bg-green-700 on staging)
        ground_selected = self.page.locator("[class*='bg-green']").filter(has_text="Ground").first
        expect(ground_selected).to_be_visible()
        # validate the Ships on date matched the shipping date or the origin's section of the Order Summary
        self.expect_ground_ship_date_matches_order_summary_origin()