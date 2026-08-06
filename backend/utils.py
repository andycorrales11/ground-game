"""
Shared utility functions for the backend.
"""
import re

# The canonical scoring formats. calculate_vorp rejects anything else, and the
# database column names are derived from these.
SCORING_FORMATS = ('STD', 'PPR', 'HalfPPR')

# Everything the outside world calls these formats. Keys are stripped to letters
# only, so 'half_ppr', 'HALF-PPR' and 'Half PPR' all collapse to 'halfppr'.
_FORMAT_ALIASES = {
    'std': 'STD',
    'standard': 'STD',
    'ppr': 'PPR',
    'fullppr': 'PPR',
    'halfppr': 'HalfPPR',
    'half': 'HalfPPR',
}

# The snake_case stem each format uses in database and big-board column names.
# Note 'HalfPPR'.lower() is 'halfppr', NOT the 'half_ppr' the columns use -- that
# gap is what made every half-PPR draft fail with a KeyError.
_FORMAT_COLUMN_STEMS = {'STD': 'std', 'PPR': 'ppr', 'HalfPPR': 'half_ppr'}


def format_column_stem(scoring_format, default='STD'):
    """The snake_case stem for a format, e.g. 'HalfPPR' -> 'half_ppr'."""
    return _FORMAT_COLUMN_STEMS[normalize_scoring_format(scoring_format, default)]


def points_column(scoring_format, default='STD'):
    """
    The big board's projection column for a format, e.g. 'fantasy_points_half_ppr'.

    Use this everywhere rather than building the name inline: create_vbd_big_board
    renames the column using one spelling and calculate_vorp used to look it up
    using another, so half-PPR raised a KeyError on every draft.
    """
    return f"fantasy_points_{format_column_stem(scoring_format, default)}"


def normalize_scoring_format(scoring_format, default='STD'):
    """
    Maps any spelling of a scoring format onto one of SCORING_FORMATS.

    Sleeper sends 'half_ppr' and the draft setup form sends 'HALF_PPR'; both used
    to be passed through .upper() into 'HALF_PPR', which calculate_vorp rejects.
    Note that 'HalfPPR' is mixed-case by design -- do not upper() the result.
    """
    if not scoring_format:
        return default
    key = re.sub(r'[^a-z]', '', str(scoring_format).lower())
    return _FORMAT_ALIASES.get(key, default)


# Canonical format -> the suffix used in database and DataFrame column names
# (std_adp, ppr_proj_pts, fantasy_points_half_ppr, ...).
_FORMAT_SUFFIXES = {
    'STD': 'std',
    'PPR': 'ppr',
    'HalfPPR': 'half_ppr',
}


def scoring_format_suffix(scoring_format):
    """
    Returns the column-name suffix for a scoring format.

    The single source of truth for this mapping. It used to be spelled out
    inline in three places, and one of them omitted the halfppr -> half_ppr
    step, so every HalfPPR draft died looking for 'fantasy_points_halfppr'.
    """
    return _FORMAT_SUFFIXES[normalize_scoring_format(scoring_format)]


def normalize_name(player_name):
    """Normalizes player name by lowercasing and removing special characters."""
    if not isinstance(player_name, str):
        return None
    # Remove 'Sr.', 'Jr.', 'III', etc.
    name = re.sub(r'\s+(Sr\.|Jr\.|III|II|IV)$', '', player_name)
    # Remove apostrophes and periods, and replace spaces with underscores
    return re.sub(r"['.]", '', name).lower().replace(' ', '_')
