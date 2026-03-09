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