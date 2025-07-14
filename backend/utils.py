"""
Shared utility functions for the backend.
"""
import re

def normalize_name(name: str) -> str:
    """Normalizes player names for consistent matching."""
    if not isinstance(name, str):
        return name
    name = name.lower()
    name = name.replace("'", "") # Remove apostrophes
    name = re.sub(r'[^a-z0-9\s]', '', name)  # Remove other non-alphanumeric except spaces
    name = re.sub(r'(jr|sr|ii|iii|iv)$', '', name)  # Remove common suffixes at end
    return name.strip()
