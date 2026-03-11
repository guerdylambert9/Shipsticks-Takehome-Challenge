import re
import pytest
from playwright.sync_api import Page, expect
from pages.booking_step1_page import BookingStep1Page
from exceptions.booking_exceptions import *

@pytest.fixture(scope="function")
def booking_page(page: Page) -> BookingStep1Page:
    """Fixture for fresh BookingStep1Page instance per test."""
    booking = BookingStep1Page(page)
    booking.navigate_to_landing()
    booking.click_get_started()
    return booking


@pytest.mark.happy_path
def test_landing_and_get_started_navigates_to_booking(booking_page: BookingStep1Page) -> None:
    """Happy path: landing -> Get Started -> booking step 1 page loads."""
    # Accept with or without www (site may redirect to www)
    expect(booking_page.page).to_have_url(
        re.compile(r"https://(www\.)?app\.staging\.shipsticks\.com/book/ship")
    )

    # Select shipment type
    booking_page.select_shipment_type_one_way()

    # Enter origin (handle async autocomplete)
    booking_page.enter_origin("1234 Main Street, Los Angeles, CA, USA")

    # Enter destination (handle async autocomplete)
    booking_page.enter_destination("4321 Main St, Miami Lakes, FL, USA")

    # Select item
    booking_page.select_item_golf_bag_standard()

    # Shipment Speeds is hidden until a date is selected
    expect(booking_page.shipment_speeds_section()).to_be_hidden()

    # Select delivery date (handle async picker)
    booking_page.select_delivery_date("April 8, 2026")  # Adjust format if picker uses day only; e.g., "8"

    # Shipment Speeds is visible after a date is selected
    expect(booking_page.shipment_speeds_section()).to_be_visible()

    # Select service level
    booking_page.select_service_level_ground()