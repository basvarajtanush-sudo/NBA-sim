import nflreadpy as nfl
import math

SEASONS = [2021, 2022, 2023, 2024]
EPA_HOME_ADV = 0.05   # starting guess, will tune
EPA_K = 3            # starting guess, will tune

def get_team_game_epa(season):
    pbp = nfl.load_pbp([season])
    plays = pbp.to_dicts()
    plays = [p for p in plays if p["epa"] is not None and p["play_type"] in ("pass", "run")]

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

def get_avg_net_epa_before(team, week, offense_epa, defense_epa):
    off_values = []
    def_values = []

    for (t, w), values in offense_epa.items():
        if t == team and w < week:
            off_values.extend(values)
    for (t, w), values in defense_epa.items():
        if t == team and w < week:
            def_values.extend(values)

    if len(off_values) < 50:
        return None

    avg_off_epa = sum(off_values) / len(off_values)
    avg_def_epa = sum(def_values) / len(def_values)
    return avg_off_epa - avg_def_epa

def epa_to_win_prob(epa_diff):
    return 1 / (1 + math.exp(-EPA_K * epa_diff))

def american_to_implied_prob(odds):
    if odds < 0:
        return -odds / (-odds + 100)
    else:
        return 100 / (odds + 100)

def remove_vig(odds_a, odds_b):
    prob_a = american_to_implied_prob(odds_a)
    prob_b = american_to_implied_prob(odds_b)
    total = prob_a + prob_b
    return prob_a / total, prob_b / total

def payout_if_win(odds, stake=100):
    if odds < 0:
        return stake * 100 / abs(odds)
    else:
        return stake * odds / 100

schedule = nfl.load_schedules(SEASONS)
games = schedule.to_dicts()
games = [g for g in games if g["home_score"] is not None]
games.sort(key=lambda g: (g["season"], g["week"]))

results = []
epa_cache = {}

for g in games:
    season = g["season"]
    week = g["week"]
    home, away = g["home_team"], g["away_team"]
    home_ml, away_ml = g["home_moneyline"], g["away_moneyline"]

    if season not in epa_cache:
        print(f"Loading play-by-play for {season}...")
        epa_cache[season] = get_team_game_epa(season)

    offense_epa, defense_epa = epa_cache[season]

    home_net_epa = get_avg_net_epa_before(home, week, offense_epa, defense_epa)
    away_net_epa = get_avg_net_epa_before(away, week, offense_epa, defense_epa)

    if home_net_epa is not None and away_net_epa is not None and home_ml is not None and away_ml is not None:
        epa_diff = (home_net_epa + EPA_HOME_ADV) - away_net_epa
        model_prob_home = epa_to_win_prob(epa_diff)
        fair_home, fair_away = remove_vig(home_ml, away_ml)
        edge = model_prob_home - fair_home
        actual_home_win = 1 if g["home_score"] > g["away_score"] else 0

        results.append({
            "week": week, "season": season, "home": home, "away": away,
            "model_prob_home": model_prob_home, "fair_home": fair_home,
            "edge": edge, "actual_home_win": actual_home_win,
            "home_ml": home_ml, "away_ml": away_ml,
            "epa_diff": epa_diff,
        })

print(f"Backtested {len(results)} games")

bins = [(0, .3), (.3, .4), (.4, .5), (.5, .6), (.6, .7), (.7, 1.0)]
print("\n--- Calibration (EPA model) ---")
for lo, hi in bins:
    bucket = [r for r in results if lo <= r["model_prob_home"] < hi]
    if bucket:
        predicted_avg = sum(r["model_prob_home"] for r in bucket) / len(bucket)
        actual_rate = sum(r["actual_home_win"] for r in bucket) / len(bucket)
        print(f"{lo:.0%}-{hi:.0%}: n={len(bucket)}, model avg={predicted_avg:.1%}, actual win rate={actual_rate:.1%}")

EDGE_THRESHOLD = 0.03
bankroll = 0
bets_placed = 0

for r in results:
    if r["edge"] > EDGE_THRESHOLD:
        odds = r["home_ml"]
        won = r["actual_home_win"] == 1
    elif r["edge"] < -EDGE_THRESHOLD:
        odds = r["away_ml"]
        won = r["actual_home_win"] == 0
    else:
        continue
    bets_placed += 1
    bankroll += payout_if_win(odds) if won else -100

print(f"\n--- Betting Sim (EPA model) (${'{:.2f}'.format(bankroll)} profit over {bets_placed} bets, $100 flat stake) ---")
print("\n--- Testing different EPA_K values ---")

def epa_to_win_prob_k(epa_diff, k):
    return 1 / (1 + math.exp(-k * epa_diff))

# rebuild model_prob_home for each candidate k, using the epa_diff already implied by home_net_epa/away_net_epa
# we need epa_diff stored per result, so add that first — see note below

for test_k in [3, 3.5, 4, 4.5, 5]:    
    total_error = 0
    bucket_count = 0
    for lo, hi in bins:
        bucket = [r for r in results if lo <= epa_to_win_prob_k(r["epa_diff"], test_k) < hi]
        if bucket:
            predicted_avg = sum(epa_to_win_prob_k(r["epa_diff"], test_k) for r in bucket) / len(bucket)
            actual_rate = sum(r["actual_home_win"] for r in bucket) / len(bucket)
            total_error += abs(predicted_avg - actual_rate)
            bucket_count += 1
    avg_error = total_error / bucket_count if bucket_count else None
    print(f"k={test_k}: avg calibration error = {avg_error:.1%}" if avg_error else f"k={test_k}: no data")

