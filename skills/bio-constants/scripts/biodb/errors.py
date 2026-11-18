"""Exception types. BlindError maps to exit code 2 (cannot check, never a pass)."""


class BlindError(Exception):
    """The value could not be determined (network/API failure or ambiguous record)."""
