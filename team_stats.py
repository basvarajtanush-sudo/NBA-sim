import nflreadpy as nfl

def get_points_per_game(season=2026):
    schedule = nfl.load_schedules([season])
    games = schedule.to_dicts()

    points_scored = {}
    points_allowed = {}
    games_played = {}

    for g in games:
        if g["home_score"] is None or g["away_score"] is None:
            continue

        home = g["home_team"]
        away = g["away_team"]
        home_score = g["home_score"]
        away_score = g["away_score"]

        points_scored[home] = points_scored.get(home, 0) + home_score
        points_scored[away] = points_scored.get(away, 0) + away_score

        points_allowed[home] = points_allowed.get(home, 0) + away_score
        points_allowed[away] = points_allowed.get(away, 0) + home_score

        games_played[home] = games_played.get(home, 0) + 1
        games_played[away] = games_played.get(away, 0) + 1

    ppg = {}
    for team in games_played:
        ppg[team] = {
            "points_per_game": round(points_scored[team] / games_played[team], 1),
            "points_allowed_per_game": round(points_allowed[team] / games_played[team], 1),
            "games_played": games_played[team],
        }

    return ppg


def get_team_abbreviation(full_name):
    teams = nfl.load_teams()
    team_rows = teams.filter(teams["team_name"] == full_name).to_dicts()
    if not team_rows:
        return None
    return team_rows[0]["team_abbr"]

def get_team_profile(team, season=2026):
    team_stats = nfl.load_team_stats(seasons=[season])
    team_rows = team_stats.filter(team_stats["team"] == team).to_dicts()

    if not team_rows:
        return None

    games_played = len(team_rows)

    def avg(field):
        return round(sum(row[field] for row in team_rows) / games_played, 1)

    def total(field):
        return sum(row[field] for row in team_rows)

    profile = {
        "sacks_allowed_per_game": avg("sacks_suffered"),
        "games_played": games_played,
        "passing_yards_per_game": avg("passing_yards"),
        "rushing_yards_per_game": avg("rushing_yards"),
        "touchdowns_per_game": round(
            (total("passing_tds") + total("rushing_tds") + total("receiving_tds")) / games_played, 1
        ),
        "turnovers_per_game": round(
            (total("passing_interceptions") + total("fumbles_lost_total")) / games_played, 1
        ),
        "sacks_per_game": avg("def_sacks"),
        "takeaways_per_game": round(
            (total("def_interceptions") + total("fumble_recovery_opp")) / games_played, 1
        ),
    }

    ppg = get_points_per_game(season)
    if team in ppg:
        profile["points_per_game"] = ppg[team]["points_per_game"]
        profile["points_allowed_per_game"] = ppg[team]["points_allowed_per_game"]

    return profile