"""Reference lists behind the application form: the industries the system recognises and the loan purposes it offers."""

from __future__ import annotations

# (display name, policy tag, NAICS code)
INDUSTRIES = [
    ("Restaurant and catering", "restaurant", "722511"),
    ("Auto repair shop", "auto_repair", "811111"),
    ("Software consulting", "software", "541511"),
    ("Light manufacturing", "manufacturing", "332710"),
    ("Apparel retail", "retail", "448140"),
    ("Freight and trucking", "logistics", "484110"),
    ("Medical clinic", "healthcare", "621111"),
    ("Construction contractor", "construction", "236220"),
    ("Wholesale distribution", "wholesale", "423990"),
    ("Landscaping services", "landscaping", "561730"),
]
# Industries that bank policies commonly prohibit. They are offered like any other so that the policy, not the form, decides.
PROHIBITED = [
    ("Cannabis dispensary", "cannabis", "453998"),
    ("Firearms and ammunition retailer", "firearms", "451110"),
    ("Casino and gambling operator", "gambling", "713210"),
    ("Adult entertainment venue", "adult_entertainment", "713990"),
    ("Cryptocurrency exchange", "crypto_exchange", "523130"),
]
PURPOSES = ["equipment purchase", "working capital", "expansion", "inventory build", "debt refinancing", "vehicle fleet"]
