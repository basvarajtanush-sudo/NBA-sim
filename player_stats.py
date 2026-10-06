import nflreadpy as nfl

def _build_game_site_lookup(season):
    schedule = nfl.load_schedules([season])
    games = schedule.to_dicts()
    return {g["game_id"]: (g["home_team"], g["away_team"]) for g in games}

def get_player_profile(player_name, current_season=2026, prior_season=2025, upcoming_is_home=None):
    current_stats = nfl.load_player_stats([current_season])
    prior_stats = nfl.load_player_stats([prior_season])

    current_rows = current_stats.filter(
        (current_stats["player_display_name"] == player_name) &
        (current_stats["season_type"] == "REG")
    ).to_dicts()
    prior_rows = prior_stats.filter(
        (prior_stats["player_display_name"] == player_name) &
        (prior_stats["season_type"] == "REG")
    ).to_dicts()

    if not current_rows and not prior_rows:
        return None

    current_rows.sort(key=lambda r: r["week"])
    prior_rows.sort(key=lambda r: r["week"])

    # Figure out home/away for each historical game, using the schedule
    current_sites = _build_game_site_lookup(current_season)
    prior_sites = _build_game_site_lookup(prior_season)

    def tag_site(row, site_lookup):
        home_team, away_team = site_lookup.get(row["game_id"], (None, None))
        if row["team"] == home_team:
            return "home"
        elif row["team"] == away_team:
            return "away"
        return None

    games_so_far = len(current_rows)
    prior_weight = max(0.05, 0.4 - (games_so_far * 0.035))

    weighted_rows = []
    home_games = 0
    away_games = 0

    for row in prior_rows:
        site = tag_site(row, prior_sites)
        weight = prior_weight
        if upcoming_is_home is not None and site is not None:
            if (upcoming_is_home and site == "home") or (not upcoming_is_home and site == "away"):
                weight *= 1.25  # bonus for matching site
        weighted_rows.append((row, weight))
        if site == "home": home_games += 1
        elif site == "away": away_games += 1

    for i, row in enumerate(current_rows):
        site = tag_site(row, current_sites)
        weight = 1.0 + (i * 0.25)
        if upcoming_is_home is not None and site is not None:
            if (upcoming_is_home and site == "home") or (not upcoming_is_home and site == "away"):
                weight *= 1.25
        weighted_rows.append((row, weight))
        if site == "home": home_games += 1
        elif site == "away": away_games += 1

    total_weight = sum(w for _, w in weighted_rows)

    def weighted_avg(field):
        return round(sum(row[field] * w for row, w in weighted_rows) / total_weight, 1)

    def weighted_avg_safe(field):
        valid = [(row, w) for row, w in weighted_rows if row.get(field) is not None]
        if not valid:
            return None
        vw = sum(w for _, w in valid)
        return round(sum(row[field] * w for row, w in valid) / vw * 100, 1)

    def get_weighted_samples(field):
        """Returns [(value, weight), ...] for Monte Carlo resampling \u2014
        the same recency/home-away weighting used everywhere else,
        just not collapsed into a single average."""
        return [(row[field], w) for row, w in weighted_rows if row.get(field) is not None]

    def weighted_total(field):
        return sum(row[field] * w for row, w in weighted_rows)
    games_played = len(current_rows)


    profile = {
        "team": current_rows[-1]["team"] if current_rows else prior_rows[-1]["team"],
        "position": current_rows[-1]["position"] if current_rows else prior_rows[-1]["position"],
        "games_played": games_played,
        "games_used_in_average": len(weighted_rows),
        "home_games_sampled": home_games,
        "away_games_sampled": away_games,
        "passing_yards_per_game": weighted_avg("passing_yards"),
        "rushing_yards_per_game": weighted_avg("rushing_yards"),
        "receiving_yards_per_game": weighted_avg("receiving_yards"),
        "receptions_per_game": weighted_avg("receptions"),
        "touchdowns_per_game": round(
            (weighted_total("passing_tds") + weighted_total("rushing_tds") + weighted_total("receiving_tds")) / total_weight, 1
        ),
        "target_share_pct": weighted_avg_safe("target_share"),
        "air_yards_share_pct": weighted_avg_safe("air_yards_share"),
    }
    profile["_weighted_samples"] = {
        "passing_yards": get_weighted_samples("passing_yards"),
        "rushing_yards": get_weighted_samples("rushing_yards"),
        "receiving_yards": get_weighted_samples("receiving_yards"),
        "receptions": get_weighted_samples("receptions"),
    }

    return profile

profile = get_player_profile("Christian Watson")
print(profile)


