import nflreadpy as nfl

def get_team_game_epa(season):
    pbp = nfl.load_pbp([season])
    plays = pbp.to_dicts()

    # keep only real offensive plays with a valid epa value
    plays = [p for p in plays if p["epa"] is not None and p["play_type"] in ("pass", "run")]

    # (team, week) -> list of epa values, split by offense vs defense
    offense_epa = {}
    defense_epa = {}

    for p in plays:
        week = p["week"]
        off_team = p["posteam"]
        def_team = p["defteam"]
        epa = p["epa"]

        if off_team:
            offense_epa.setdefault((off_team, week), []).append(epa)
        if def_team:
            defense_epa.setdefault((def_team, week), []).append(epa)

    return offense_epa, defense_epa

offense_epa, defense_epa = get_team_game_epa(2023)
print("KC offense week 1 sample size:", len(offense_epa.get(("KC", 1), [])))
print("KC offense week 1 avg epa:", sum(offense_epa[("KC", 1)]) / len(offense_epa[("KC", 1)]))

def get_avg_net_epa_before(team, week, offense_epa, defense_epa):
    off_values = []
    def_values = []

    for (t, w), values in offense_epa.items():
        if t == team and w < week:
            off_values.extend(values)

    for (t, w), values in defense_epa.items():
        if t == team and w < week:
            def_values.extend(values)

    if len(off_values) < 50:  # rough floor for a meaningful sample of plays
        return None

    avg_off_epa = sum(off_values) / len(off_values)
    avg_def_epa = sum(def_values) / len(def_values)

    return avg_off_epa - avg_def_epa

net_epa = get_avg_net_epa_before("KC", 8, offense_epa, defense_epa)
print("KC net EPA before week 8:", net_epa)