"""
Shared utility functions for the backend.
"""
import re

def normalize_name(player_name):
    """Normalizes player name by lowercasing and removing special characters."""
    if not isinstance(player_name, str):
        return None
    # Remove 'Sr.', 'Jr.', 'III', etc.
    name = re.sub(r'\s+(Sr\.|Jr\.|III|II|IV)$', '', player_name)
    # Remove apostrophes and periods, and replace spaces with underscores
    return re.sub(r"['.]", '', name).lower().replace(' ', '_')
