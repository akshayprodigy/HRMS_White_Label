"""Fixed areas of authority a manager or cover can be limited to."""
SUBDOMAINS = {
    "leave": "Leave", "attendance": "Attendance", "roster": "Roster",
    "expense": "Expenses and travel", "asset": "Assets", "pay": "Pay",
    "people": "People", "business": "Business",
}


def validate(values) -> frozenset:
    bad = sorted(set(values or ()) - set(SUBDOMAINS))
    if bad:
        raise ValueError(f"Unknown subdomain: {', '.join(bad)}")
    return frozenset(values or ())
