"""Shared utility helpers for the AI Intelligence Dashboard backend."""

import sys


def check_python_version() -> None:
    """Verify that the running Python interpreter meets the minimum version requirement.

    Prints a descriptive error message to stderr and exits with status code 1 if the
    current Python version is older than 3.11.  Call this at the very start of any
    entry-point script so the user receives a clear diagnostic instead of a cryptic
    syntax or import error.
    """
    required = (3, 11)
    if sys.version_info < required:
        required_str = ".".join(str(v) for v in required)
        current_str = ".".join(str(v) for v in sys.version_info[:3])
        print(
            f"ERROR: Python {required_str} or newer is required, "
            f"but you are running Python {current_str}.\n"
            f"Please upgrade your Python installation and recreate the virtual environment.\n"
            f"  https://www.python.org/downloads/",
            file=sys.stderr,
        )
        sys.exit(1)
