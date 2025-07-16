"""
Service for interacting with the Sleeper API.
"""
import logging
import requests
import pandas as pd
from . import data_service
from backend import utils

def get_draft_settings(draft_id: str) -> dict | None:
    """
    Fetches the settings for a specific Sleeper draft.

    Args:
        draft_id: The ID of the Sleeper draft.

    Returns:
        A dictionary with the draft settings or None if an error occurs.
    """
    api_url = f"https://api.sleeper.app/v1/draft/{draft_id}"
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Extract the relevant settings
        settings = {
            'rounds': data.get('settings', {}).get('rounds', 15),
            'teams': data.get('settings', {}).get('teams', 12),
            'order': data.get('type', 'snake'),
            'format': data.get('metadata', {}).get('scoring_type', 'std').upper(),
            'slot_to_roster_id': data.get('slot_to_roster_id', {})
        }
        logging.info(f"Successfully fetched draft settings: {settings}")
        return settings
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch draft settings from Sleeper API: {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred in get_draft_settings: {e}")
        return None

def get_all_picks(draft_id: str) -> list:
    """
    Fetches all picks that have been made in a Sleeper draft.
    
    Args:
        draft_id: The ID of the Sleeper draft.

    Returns:
        A list of pick objects.
    """
    api_url = f"https://api.sleeper.app/v1/draft/{draft_id}/picks"
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        picks_data = response.json()
        logging.info(f"Successfully fetched {len(picks_data)} picks from Sleeper.")
        return picks_data
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch picks from Sleeper API: {e}")
        return []
    except Exception as e:
        logging.error(f"An unexpected error occurred in get_all_picks: {e}")
        return []
