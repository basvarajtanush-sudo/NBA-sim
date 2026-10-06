import nflreadpy as nfl

def get_defense_vs_position(team_abbr, season=2026):
    stats = nfl.load_player_stats([season])
    rows = stats.filter(
        (stats["opponent_team"] == team_abbr) &
        (stats["season_type"] == "REG")
    ).to_dicts()

    if not rows:
        return None

    game_ids = set(row["game_id"] for row in rows)
    n_games = len(game_ids)

    relevant_positions = {"QB", "RB", "WR", "TE"}

    totals = {}
    for row in rows:
        pos = row["position"]
        if pos not in relevant_positions:
            continue
        if pos not in totals:
            totals[pos] = {
                "receiving_yards": 0, "receptions": 0, "rushing_yards": 0,
                "receiving_epa": 0.0, "rushing_epa": 0.0,
            }
        totals[pos]["receiving_yards"] += row["receiving_yards"] or 0
        totals[pos]["receptions"] += row["receptions"] or 0
        totals[pos]["rushing_yards"] += row["rushing_yards"] or 0
        totals[pos]["receiving_epa"] += row["receiving_epa"] or 0.0
        totals[pos]["rushing_epa"] += row["rushing_epa"] or 0.0

    profile = {}
    for pos, vals in totals.items():
        profile[pos] = {
            "receiving_yards_allowed_per_game": round(vals["receiving_yards"] / n_games, 1),
            "receptions_allowed_per_game": round(vals["receptions"] / n_games, 1),
            "rushing_yards_allowed_per_game": round(vals["rushing_yards"] / n_games, 1),
            "receiving_epa_allowed_per_game": round(vals["receiving_epa"] / n_games, 2),
            "rushing_epa_allowed_per_game": round(vals["rushing_epa"] / n_games, 2),
        }

    return profile


def get_league_average_epa(position, stat_type="receiving", season=2026):
    """
    stat_type: 'receiving' or 'rushing'
    Returns the league-average EPA-allowed per game for a given position,
    across all 32 teams' defenses.
    """
    teams = nfl.load_teams()
    all_abbrs = teams["team_abbr"].to_list()

    field = f"{stat_type}_epa_allowed_per_game"
    values = []

    for abbr in all_abbrs:
        profile = get_defense_vs_position(abbr, season=season)
        if profile and position in profile:
            values.append(profile[position][field])

    if not values:
        return None
    return round(sum(values) / len(values), 3)


def get_pass_defense_epa(team_abbr, season=2026):
    """
    Returns the average EPA allowed per pass play by this team's defense,
    across all passing plays faced this season \u2014 a true measure of pass
    defense strength, independent of which opposing player threw it.
    """
    pbp = nfl.load_pbp([season])
    plays = pbp.to_dicts()

    pass_plays = [
        p for p in plays
        if p.get("defteam") == team_abbr
        and p.get("play_type") == "pass"
        and p.get("epa") is not None
    ]

    if not pass_plays:
        return None

    avg_epa = sum(p["epa"] for p in pass_plays) / len(pass_plays)
    return round(avg_epa, 3)


