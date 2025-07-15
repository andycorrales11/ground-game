
import pytest
from backend.services.draft_service import get_user_picks

def test_get_user_picks_snake():
    """Tests get_user_picks for a snake draft."""
    picks = get_user_picks(pick=1, order='snake', teams=12, rounds=4)
    assert picks == [1, 24, 25, 48]

def test_get_user_picks_standard():
    """Tests get_user_picks for a standard draft."""
    picks = get_user_picks(pick=3, order='normal', teams=10, rounds=3)
    assert picks == [3, 13, 23]

