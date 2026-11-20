"""Test configuration: demonstration data is switched on for the suite (the product ships with it off)."""

import os

os.environ.setdefault("WEALTHPILOT_DEMO", "1")
