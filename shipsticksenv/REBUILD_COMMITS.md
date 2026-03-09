# Step-by-step rebuild: one commit per issue

Use this guide to recreate the project in a **new repository** and push **one commit per fixed issue** to demonstrate how you work through each problem.

**How to use**

1. Create a new repo (e.g. `Shipsticks-challenge-rebuild`) and clone it. Do **not** copy the existing `shipsticksenv` into it.
2. Work **inside the new repo**. For each step below, make the stated changes, then run `git add`, `git commit -m "..."`, and `git push`.
3. Use the **current project** (`shipsticksenv/` in this repo) as reference: when the guide says “copy from current project”, copy from `shipsticksenv/` (or the path given).
4. Run tests from inside the new repo with the venv activated: `cd <new-repo> && source venv/bin/activate && pytest tests/ -m happy_path --headed` (adjust if your venv lives elsewhere).

---

## Commit 1: Project setup and config

**Message:** `chore: add project setup, config, and pytest + Playwright`

**Issue:** Need a runnable project with config and test discovery.

**Files to create:**

- `requirements.txt` – Copy from current project `shipsticksenv/requirements.txt`.
- `pytest.ini` – Copy from current project `shipsticksenv/pytest.ini`.
- `conftest.py` – Copy from current project `shipsticksenv/conftest.py` (only the `sys.path` and `pytest.fixture(scope="function")` for `booking_page`; you can add `keep_browser_open` later or omit it for now).
- `config/config.py` – Copy from current project `shipsticksenv/config/config.py`.
- `config/__init__.py` – Empty or `from .config import BASE_URL`.
- `.env.example` – One line: `BASE_URL=https://app.staging.shipsticks.com`.
- `exceptions/booking_exceptions.py` – Copy from current project `shipsticksenv/exceptions/booking_exceptions.py`.
- `exceptions/__init__.py` – Empty or import the exceptions.
- `pages/__init__.py` – Empty.
- `retries/retry.py` – Copy from current project `shipsticksenv/retries/retry.py`.
- `retries/__init__.py` – Empty or import `retry_on_timeout`.
- `tests/test_step1_booking.py` – Minimal: fixture `booking_page(page)` that instantiates `BookingStep1Page(page)` and returns it (no `navigate_to_landing`/`click_get_started` until Commit 2). One test that does `booking_page.page.goto(booking_page.url)` and `expect(booking_page.page).to_have_url(re.compile(r"book/ship"))` so the test runs and passes once the page object has `url`.
- `pages/booking_step1_page.py` – Minimal: `from playwright.sync_api import Page`; `class BookingStep1Page:` with `__init__(self, page: Page)` and `self.url = f"{BASE_URL}/book/ship"` (import BASE_URL from config). No other methods yet.

Create venv, install deps, `playwright install`, create `.env` from `.env.example`. Then commit and push.

---

## Commit 2: Landing page and Get Started

**Message:** `feat: add landing navigation and Get Started click to reach booking`

**Issue:** Test must start from landing and reach `/book/ship` via the visible Get Started CTA.

**Files to change:**

- `pages/booking_step1_page.py` – Add `navigate_to_landing()` (goto BASE_URL, assert title with regex for “Ship”/“Golf”) and `click_get_started()` (scroll to “Great golf trips”, click the second “Get started” link/button with `locator("a, button").filter(has_text=re.compile(r"Get started", re.I)).nth(1)`, then `page.wait_for_url("**/book/ship")`). Add `get_started_button()` if you want a dedicated locator.
- `tests/test_step1_booking.py` – Update `booking_page` fixture to call `booking_page.navigate_to_landing()` and `booking_page.click_get_started()` after creating the page object. Happy-path test can call only those two for this commit (or add the next step when you add it).

Commit and push.

---

## Commit 3: Trip type One way (Headless UI dropdown)

**Message:** `fix: select One way from trip type dropdown (Headless UI portal)`

**Issue:** Trip type is a Headless UI listbox; “One way” lives in `#headlessui-portal-root`, not next to the trigger.

**Files to change:**

- `pages/booking_step1_page.py` – Add `shipment_type_dropdown()` (e.g. `get_by_label("Trip Type").or_(get_by_text("Round trip").first)`). Add `select_shipment_type_one_way()`: click dropdown, then in `#headlessui-portal-root` wait for and click option with name matching `One[- ]way`.
- `tests/test_step1_booking.py` – In happy-path test, add `booking_page.select_shipment_type_one_way()`.

Commit and push.

---

## Commit 4: Origin autocomplete with retry

**Message:** `feat: enter origin address with autocomplete and retry on timeout`

**Issue:** Autocomplete options appear asynchronously; test can timeout waiting for the list.

**Files to change:**

- `pages/booking_step1_page.py` – Add `origin_input()` (placeholder "Choose origin..."). Add helper `_fill_and_select_address(input_locator, address)` (fill, press ArrowDown, wait for option by regex from address, click). Add `_option_for_address(address)` to build regex (e.g. street, city, state with CA|California, FL|Florida). Add `enter_origin(address)` that calls `_fill_and_select_address(origin_input(), address)` inside `retry_on_timeout(..., max_attempts=3, delay_seconds=2.0)`.
- `retries/retry.py` – Already in place from Commit 1.
- `tests/test_step1_booking.py` – In happy-path test, add `booking_page.enter_origin("1234 Main Street, Los Angeles, CA, USA")`.

Commit and push.

---

## Commit 5: Destination autocomplete and destination note dialog

**Message:** `fix: destination autocomplete and dismiss "I understand" dialog`

**Issue:** Destination has autocomplete like origin; after selecting, a “Please note before proceeding” dialog with “I understand” can block the flow.

**Files to change:**

- `pages/booking_step1_page.py` – Add `destination_input()` (placeholder "Choose destination..."). Add `enter_destination(address)`: call `_fill_and_select_address(destination_input(), address)` then `_dismiss_destination_note_dialog_if_present()` inside `retry_on_timeout`. Add `_dismiss_destination_note_dialog_if_present()`: wait for button "I understand", click it, wait for `get_by_role("dialog")` to be hidden (use try/except; no-op if dialog not present).
- `tests/test_step1_booking.py` – In happy-path test, add `booking_page.enter_destination("4321 Main St, Miami Lakes, FL, USA")`.

Commit and push.

---

## Commit 6: Golf Bags quantity (fill 1)

**Message:** `feat: set Golf Bags quantity to 1 via input fill`

**Issue:** “+” button was covered by overlays; filling the input is reliable.

**Files to change:**

- `pages/booking_step1_page.py` – In `select_item_golf_bag_standard()`: dismiss destination note and cookie consent if present, wait for “Golf Bags” text and scroll, locate `input[name="productLineCounters.0"]`.first, fill with "1", assert value "1". Add `_dismiss_cookie_consent_if_present()` (e.g. click `#onetrust-accept-btn-handler` or button “Accept all” if visible).
- `tests/test_step1_booking.py` – In happy-path test, add `booking_page.select_item_golf_bag_standard()`.

Commit and push.

---

## Commit 7: Validate Standard size selected by default

**Message:** `feat: assert Max 42 lb. Standard is selected by default for Golf Bags`

**Issue:** After setting quantity to 1, confirm the default size is selected.

**Files to change:**

- `pages/booking_step1_page.py` – At end of `select_item_golf_bag_standard()`, add: `standard_option = page.get_by_role("radio", name=re.compile(r"Max 42 lb\.\s*Standard|Standard", re.I)); expect(standard_option.first).to_be_checked()`.

Commit and push.

---

## Commit 8: Close modal/overlay before date picker (first pass)

**Message:** `fix: close Headless UI modal before opening date picker (Escape, backdrop, I understand)`

**Issue:** A modal or overlay covers the page so the “Please select a date” button is not visible; test times out.

**Files to change:**

- `pages/booking_step1_page.py` – Add `_headlessui_dialog()` returning `page.locator("#headlessui-portal-root [role='dialog']")`. Add `_close_any_modal_overlay()`: in a loop, try “I understand” click, then backdrop click (`#headlessui-portal-root div.fixed[aria-hidden='true']`), then Escape; wait for dialog hidden (dynamic). Call `_close_any_modal_overlay()` at the start of `select_delivery_date()` (which you’ll add in a later commit) and wait for dialog hidden before scrolling to delivery section. For this commit you can add a minimal `select_delivery_date(date_str)` that only does: dismiss dialogs, close modal, wait for dialog hidden, scroll to “delivery|date|when”, then wait for `delivery_date_picker()` to be visible (and fail here until later commits fix remaining blockers).

Add `delivery_date_picker()` locator: `get_by_role("button", name="Please select a date").or_(get_by_role("button", name="Open calendar")).or_(get_by_role("button", name=re.compile(r"calendar|select date|choose date", re.I))).first`.

Commit and push (test may still timeout at date picker).

---

## Commit 9: Detect modal open reliably

**Message:** `fix: detect Headless UI modal open via data-headlessui-state and overlay`

**Issue:** `dialog.is_visible()` can be false even when the overlay is present; need a robust “modal open” check.

**Files to change:**

- `pages/booking_step1_page.py` – Add `_is_headlessui_modal_open()`: return True if any of these is visible in `#headlessui-portal-root`: `[data-headlessui-state='open']`, `[role='dialog']`, or `div.fixed.inset-0`. Use this inside `_close_any_modal_overlay()` instead of only `dialog.is_visible()`.

Commit and push.

---

## Commit 10: Clear Headless UI portal via JS

**Message:** `fix: clear Headless UI portal with JS when modal does not close via Escape/backdrop`

**Issue:** Some modals don’t close on Escape or backdrop click; overlay stays and blocks the test.

**Files to change:**

- `pages/booking_step1_page.py` – Add `_dismiss_headlessui_portal_via_js()`: `page.evaluate` to set `document.getElementById('headlessui-portal-root').innerHTML = ''`. At the end of `_close_any_modal_overlay()`, after Escape/backdrop attempts, call this as last resort. Optionally call `_ensure_main_content_interactable()` (next commit) after it.

Commit and push.

---

## Commit 11: Clear main inert and aria-hidden

**Message:** `fix: remove inert and aria-hidden from main so content is interactable after modal close`

**Issue:** After closing the modal with JS, the app leaves `<main inert>` and `aria-hidden="true"`, so Playwright still treats main as non-interactive.

**Files to change:**

- `pages/booking_step1_page.py` – Add `_ensure_main_content_interactable()`: in `page.evaluate`, remove `inert` and `aria-hidden` from `document.querySelector('main')`, and remove `overflow: hidden` from `document.documentElement` if set. Call it after `_dismiss_headlessui_portal_via_js()` in `_close_any_modal_overlay()`, and in the “wait for date picker” logic (next commits).

Commit and push.

---

## Commit 12: Remove Playwright x-pw-glass overlay

**Message:** `fix: remove Playwright x-pw-glass overlay that blocks visibility checks`

**Issue:** Playwright injects a full-viewport overlay that can make elements fail `is_visible()` / `wait_for(state="visible")`.

**Files to change:**

- `pages/booking_step1_page.py` – Add `_remove_playwright_glass_overlay()`: `page.evaluate` to `document.querySelectorAll('x-pw-glass').forEach(el => el.remove())`. Call it after closing modals and before waiting for the date picker (in the loop and in the final block before `picker.wait_for`).

Commit and push.

---

## Commit 13: Wait for date picker while dismissing modals (polling loop)

**Message:** `fix: poll and dismiss modals until date picker is visible (second modal after scroll)`

**Issue:** A second modal can open after scrolling to the delivery section; we need to keep closing modals until the picker is visible.

**Files to change:**

- `pages/booking_step1_page.py` – Add `_wait_for_date_picker_visible_while_dismissing_modals(timeout_ms=35000)`: loop until deadline; if `_is_headlessui_modal_open()` then `_close_any_modal_overlay()`, `_remove_playwright_glass_overlay()`, `_ensure_main_content_interactable()`, short wait, continue; else if `delivery_date_picker().is_visible()` return; else short sleep. After loop, if modal still open call `_dismiss_headlessui_portal_via_js()`; then `_remove_playwright_glass_overlay()`, `_ensure_main_content_interactable()`, and `picker.wait_for(state="visible", timeout=5000)`. In `select_delivery_date()`, after scrolling to delivery section call this instead of directly waiting for the picker.

Commit and push.

---

## Commit 14: Delivery date selection (open picker, month, day, assert)

**Message:** `feat: select delivery date from calendar and assert date on page`

**Issue:** Open calendar, navigate to correct month, click day, and assert the selected date appears (picker button text changes so don’t assert on same locator).

**Files to change:**

- `pages/booking_step1_page.py` – In `select_delivery_date(date_str)`: after `_wait_for_date_picker_visible_while_dismissing_modals()`, get picker, scroll into view, click; wait for `[role='grid']`. Parse `date_str` for month name and day. Click next-month button (e.g. button with `.icon-arrow-right` or aria-label “next month”) until target month header is visible. Click enabled day: `button.rdp-day:not(.rdp-day_disabled)` with text matching day number. Assert selected date on page: `expect(page.locator("main")).to_contain_text(re.compile(r"Apr(il)?\s*\d{1,2},?\s*2026|2026", re.I))` (or build regex from `date_str`).
- `tests/test_step1_booking.py` – In happy-path test, add `booking_page.select_delivery_date("April 8, 2026")`.

Commit and push.

---

## Commit 15: Service level Ground and assert green

**Message:** `feat: select Ground service level and assert it is shown in green (selected state)`

**Issue:** Select Ground and verify it appears in the green selected state.

**Files to change:**

- `pages/booking_step1_page.py` – Add `service_level_option()` (e.g. `get_by_text("Ground")`). Add `select_service_level_ground()`: click option, expect it to be checked, then expect `page.locator("[class*='bg-green']").filter(has_text="Ground").first` to be visible.
- `tests/test_step1_booking.py` – In happy-path test, add `booking_page.select_service_level_ground()`.

Commit and push.

---

## Commit 16: Continue button and Step 1 complete

**Message:** `feat: click Continue and assert Step 1 complete (ready for Step 2)`

**Issue:** Complete the flow and assert we’re ready for the next step.

**Files to change:**

- `pages/booking_step1_page.py` – Add `continue_button()` (e.g. `get_by_role("button", name="Save")`). Add `click_continue()`: expect button enabled, click, then expect e.g. “Next: Traveler Details” visible or raise `Step1CompletionError`.
- `tests/test_step1_booking.py` – In happy-path test, add `booking_page.click_continue()` (or leave commented until you want to assert Step 2).

Commit and push.

---

## Commit 17: README and documentation

**Message:** `docs: add README with setup, run, and fixes after I Understand`

**Issue:** Document setup, how to run, and all issues fixed after the “I understand” dialog (modal, overlay, main inert, x-pw-glass, etc.).

**Files to change:**

- `readme.md` – Copy from current project `shipsticksenv/readme.md`, or write: Setup (clone, venv, install, playwright install, .env), How to run (pytest commands), Key decisions (POM, locators, async waits), Item quantity (Golf Bags fill), Destination note dialog, Why we close modals, and **What we had to fix after clicking “I Understand”** (modal/overlay, second modal on scroll, x-pw-glass, main inert/aria-hidden, html overflow). Use the current readme’s “What we had to fix…” section as the source for that part.

Commit and push.

---

## Optional: Commit 18 – Keep browser open (conftest)

**Message:** `chore: add keep_browser_open fixture for debugging`

**Files to change:**

- `conftest.py` – Add autouse fixture `keep_browser_open(page)` that yields then calls `page.pause()`.

Commit and push.

---

## Reference: current project layout

Use the existing `shipsticksenv/` in this repo as the single source of truth for:

- Full `pages/booking_step1_page.py` (all methods and helpers)
- `conftest.py`, `pytest.ini`, `requirements.txt`
- `config/config.py`, `exceptions/booking_exceptions.py`, `retries/retry.py`
- `tests/test_step1_booking.py`
- `readme.md`

When a step says “copy from current project”, copy from the path under `shipsticksenv/`. When it says “add” or “change”, apply that delta on top of what you have in the new repo so that each commit only contains the change for that issue.

---

## Managing “two projects”

- **Current project** (this repo / `shipsticksenv`): Leave as-is; it’s your reference and the final working state.
- **New project** (e.g. `Shipsticks-challenge-rebuild`): Create a new Git repo, clone it, and follow the steps above. After each step, commit and push to show one fix at a time.

You don’t need to keep both in the same repo. Use the new repo only for the step-by-step history; use this repo when you need to copy full file contents or run the full test suite as-is.
