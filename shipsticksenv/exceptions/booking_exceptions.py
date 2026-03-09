class BookingStep1Error(Exception):
    """Base exception for Step 1 booking flow failures."""
    pass

class AddressAutocompleteError(BookingStep1Error):
    """Raised when address autocomplete fails to resolve or select the exact value."""
    pass

class DatePickerError(BookingStep1Error):
    """Raised when the requested delivery date is not available/selectable."""
    pass

class ServiceLevelError(BookingStep1Error):
    """Raised when Ground service level cannot be selected or is disabled."""
    pass

class Step1CompletionError(BookingStep1Error):
    """Raised when Step 1 does not reach the 'ready for Step 2' state."""
    pass