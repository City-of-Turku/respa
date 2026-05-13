"""Compatibility shim for doctest-modules.

Actual tests live in `accessibility/test_accessibility.py` so pytest can collect
them via the `test_*.py` pattern.
"""

from accessibility.test_accessibility import *  # noqa: F401,F403
