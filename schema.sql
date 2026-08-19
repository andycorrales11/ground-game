CREATE TABLE players (
    sleeper_id VARCHAR(255) PRIMARY KEY,
    display_name TEXT,
    normalized_name TEXT,
    team VARCHAR(10),
    pos VARCHAR(10),
    bye INT,
    std_adp FLOAT,
    half_ppr_adp FLOAT,
    ppr_adp FLOAT,
    -- Where the field drafts a player when two quarterbacks can start. Not a
    -- fourth scoring format -- a superflex league is PPR or standard like any
    -- other -- and not derivable from the three above, because no scoring table
    -- implies what the field does with quarterbacks. Selected by the lineup
    -- rather than the format, and NULL for anyone the superflex export omits
    -- (kickers, defenses, and the deep pool past ~270).
    superflex_adp FLOAT,
    std_proj_pts FLOAT,
    half_ppr_proj_pts FLOAT,
    ppr_proj_pts FLOAT
);

-- --------------------------------------------------------------------------
-- Projection inputs
--
-- The three *_proj_pts columns above are finished numbers: somebody else's
-- projection, under somebody else's scoring rules. A league that pays 6 points
-- for a passing touchdown, or a full point per catch to tight ends only, has
-- nowhere to say so.
--
-- These tables store the *inputs* instead -- how much volume a team generates,
-- and each player's share of it and efficiency with it -- so the app computes
-- points at draft time against the league's own scoring. See
-- backend/services/projection_engine.py.
--
-- The *_proj_pts columns stay: they cover kickers, defenses, and the deep pool,
-- none of which the projection source models.
-- --------------------------------------------------------------------------

-- One row per import. Keeping old sets rather than overwriting is what makes a
-- weekly re-import safe and diffable -- "the projection moved 12 points" is a
-- question you can only ask if last week's numbers still exist.
CREATE TABLE projection_sets (
    id SERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    label TEXT,
    season INT,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active BOOLEAN NOT NULL DEFAULT FALSE
);

-- Only one set feeds the board at a time. A partial unique index says so in the
-- schema instead of in a comment nobody reads.
CREATE UNIQUE INDEX one_active_projection_set
    ON projection_sets (is_active)
    WHERE is_active;

-- A team's offensive budget for the season.
CREATE TABLE projection_teams (
    set_id INT NOT NULL REFERENCES projection_sets (id) ON DELETE CASCADE,
    team VARCHAR(10) NOT NULL,
    plays DOUBLE PRECISION NOT NULL,
    pass_pct DOUBLE PRECISION NOT NULL,
    rush_ypc DOUBLE PRECISION,
    PRIMARY KEY (set_id, team)
);

-- One row per projected player.
--
-- `sleeper_id` is nullable and that is load-bearing. A player the projection
-- source lists but the board does not know still has to be stored, because the
-- share weights are *relative*: they are normalized against the sum over a
-- team's players. Drop the unmatched ones and every remaining share at that
-- team silently inflates. They are stored, projected, and then simply fail to
-- join to the board.
--
-- `player_key` is the source's own within-team identifier (the workbook's row
-- number). Nothing computes with it; it only has to be stable and unique per
-- team so a projected stat line can be handed back to the right player.
CREATE TABLE projection_players (
    set_id INT NOT NULL REFERENCES projection_sets (id) ON DELETE CASCADE,
    team VARCHAR(10) NOT NULL,
    player_key INT NOT NULL,
    sleeper_id VARCHAR(255),
    display_name TEXT NOT NULL,
    normalized_name TEXT,
    pos VARCHAR(10) NOT NULL,

    -- Relative share weights, stored raw. Never pre-normalize these: the engine
    -- renormalizes per team, which is what makes one player's share dilute his
    -- teammates'.
    w_pass DOUBLE PRECISION,
    w_rush DOUBLE PRECISION,
    w_tgt DOUBLE PRECISION,

    -- Passing rates. yds_per_comp and pass_td_pct are per completion;
    -- int_pct is per attempt.
    comp_pct DOUBLE PRECISION,
    yds_per_comp DOUBLE PRECISION,
    pass_td_pct DOUBLE PRECISION,
    int_pct DOUBLE PRECISION,

    -- Rushing rates.
    rush_ypc DOUBLE PRECISION,
    rush_td_rate DOUBLE PRECISION,

    -- Receiving rates. rec_td_rate is per reception, raw and un-normalized.
    catch_rate DOUBLE PRECISION,
    yds_per_rec DOUBLE PRECISION,
    rec_td_rate DOUBLE PRECISION,

    PRIMARY KEY (set_id, team, player_key)
);

CREATE INDEX projection_players_set_sleeper_id
    ON projection_players (set_id, sleeper_id);
