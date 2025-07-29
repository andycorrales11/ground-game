CREATE TABLE players (
    sleeper_id VARCHAR(255) PRIMARY KEY,
    display_name TEXT,
    normalized_name TEXT,
    team VARCHAR(10),
    pos VARCHAR(10),
    std_adp FLOAT,
    half_ppr_adp FLOAT,
    ppr_adp FLOAT,
    std_proj_pts FLOAT,
    half_ppr_proj_pts FLOAT,
    ppr_proj_pts FLOAT
);
