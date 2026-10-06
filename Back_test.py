import nflreadpy as nfl
import math

SEASONS = [2021, 2022, 2023, 2024]
HOME_FIELD_ADV = 2.0


schedule = nfl.load_schedules(SEASONS)
games = schedule.to_dicts()

# Only completed games, sorted by season then week
games = [g for g in games if g["home_score"] is not None]
games.sort(key=lambda g: (g["season"], g["week"]))

# team -> list of (week, points_scored, points_allowed), built as we go
team_game_log = {}

def count_prior_games(team, week, game_log):
    return len([g for g in game_log.get(team, []) if g[0] < week])

def get_avg_margin_before(team, week, game_log):
    prior_games = [g for g in game_log.get(team, []) if g[0] < week]
    if len(prior_games) < 3:  # require a minimum sample before trusting it
        return None
    total_margin = sum(g[1] - g[2] for g in prior_games)
    return total_margin / len(prior_games)

def margin_to_win_prob(margin_diff):
    k = 0.1
    return 1 / (1 + math.exp(-k * margin_diff))

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

results = []
last_season = None  

for g in games:
    week = g["week"]
    season = g["season"]
    if season != last_season:
        team_game_log.clear()
        last_season = season
    home, away = g["home_team"], g["away_team"]
    home_ml, away_ml = g["home_moneyline"], g["away_moneyline"]

    

    home_avg = get_avg_margin_before(home, week, team_game_log)
    away_avg = get_avg_margin_before(away, week, team_game_log)

    if home_avg is not None and away_avg is not None and home_ml is not None and away_ml is not None:
        margin_diff = (home_avg + HOME_FIELD_ADV) - away_avg
        model_prob_home = margin_to_win_prob(margin_diff)
        fair_home, fair_away = remove_vig(home_ml, away_ml)
        edge = model_prob_home - fair_home
        actual_home_win = 1 if g["home_score"] > g["away_score"] else 0

        results.append({
            "week": week, "home": home, "away": away,
            "model_prob_home": model_prob_home, "fair_home": fair_home,
            "edge": edge, "actual_home_win": actual_home_win,
            "home_ml": home_ml, "away_ml": away_ml,
            "home_prior_games": count_prior_games(home, week, team_game_log),
            "away_prior_games": count_prior_games(away, week, team_game_log),
        })

    # NOW update the log with this game's actual result, for future weeks
    team_game_log.setdefault(home, []).append((week, g["home_score"], g["away_score"]))
    team_game_log.setdefault(away, []).append((week, g["away_score"], g["home_score"]))

print(f"Backtested {len(results)} games")

bins = [(0, .3), (.3, .4), (.4, .5), (.5, .6), (.6, .7), (.7, 1.0)]
print("\n--- Calibration ---")
for lo, hi in bins:
    bucket = [r for r in results if lo <= r["model_prob_home"] < hi]
    if bucket:
        predicted_avg = sum(r["model_prob_home"] for r in bucket) / len(bucket)
        actual_rate = sum(r["actual_home_win"] for r in bucket) / len(bucket)
        print(f"{lo:.0%}-{hi:.0%}: n={len(bucket)}, model avg={predicted_avg:.1%}, actual win rate={actual_rate:.1%}")

print("\n--- 0-30% Bucket: Early vs Established Sample ---")
low_bucket = [r for r in results if r["model_prob_home"] < 0.3]

thin = [r for r in low_bucket if min(r["home_prior_games"], r["away_prior_games"]) < 6]
established = [r for r in low_bucket if min(r["home_prior_games"], r["away_prior_games"]) >= 6]

for label, group in [("Thin sample (<6 games)", thin), ("Established (6+ games)", established)]:
    if group:
        pred = sum(r["model_prob_home"] for r in group) / len(group)
        actual = sum(r["actual_home_win"] for r in group) / len(group)
        print(f"{label}: n={len(group)}, model avg={pred:.1%}, actual win rate={actual:.1%}")
EDGE_THRESHOLD = 0.03
bankroll = 0
bets_placed = 0

for r in results:
    if r["edge"] > EDGE_THRESHOLD:
        bet_on_home = True
        odds = r["home_ml"]
        won = r["actual_home_win"] == 1
    elif r["edge"] < -EDGE_THRESHOLD:
        bet_on_home = False
        odds = r["away_ml"]
        won = r["actual_home_win"] == 0
    else:
        continue

    bets_placed += 1
    bankroll += payout_if_win(odds) if won else -100

print(f"\n--- Betting Sim (${'{:.2f}'.format(bankroll)} profit over {bets_placed} bets, $100 flat stake) ---")
print("\n--- Heavy Favorites Only (-300 or shorter) ---")
heavy_fav_games = [r for r in results if min(r["home_ml"], r["away_ml"]) <= -300]
print(f"Games with a -300+ favorite: {len(heavy_fav_games)}")

bins = [(0, .3), (.3, .4), (.4, .5), (.5, .6), (.6, .7), (.7, 1.0)]
print("\nCalibration (heavy favorites only):")
for lo, hi in bins:
    bucket = [r for r in heavy_fav_games if lo <= r["model_prob_home"] < hi]
    if bucket:
        predicted_avg = sum(r["model_prob_home"] for r in bucket) / len(bucket)
        actual_rate = sum(r["actual_home_win"] for r in bucket) / len(bucket)
        print(f"{lo:.0%}-{hi:.0%}: n={len(bucket)}, model avg={predicted_avg:.1%}, actual win rate={actual_rate:.1%}")

bankroll_hf = 0
bets_hf = 0
for r in heavy_fav_games:
    if r["edge"] > EDGE_THRESHOLD:
        odds = r["home_ml"]
        won = r["actual_home_win"] == 1
    elif r["edge"] < -EDGE_THRESHOLD:
        odds = r["away_ml"]
        won = r["actual_home_win"] == 0
    else:
        continue
    bets_hf += 1
    bankroll_hf += payout_if_win(odds) if won else -100

print(f"\n--- Heavy Favorite Betting Sim (${'{:.2f}'.format(bankroll_hf)} profit over {bets_hf} bets) ---")

print("\n--- Heavy Favorites, High-Confidence Only (75%+) ---")
CONFIDENCE_THRESHOLD = 0.75

bankroll_hc = 0
bets_hc = 0

for r in heavy_fav_games:
    home_conf = r["model_prob_home"]
    away_conf = 1 - home_conf

    if home_conf >= CONFIDENCE_THRESHOLD and r["edge"] > EDGE_THRESHOLD:
        odds = r["home_ml"]
        won = r["actual_home_win"] == 1
    elif away_conf >= CONFIDENCE_THRESHOLD and r["edge"] < -EDGE_THRESHOLD:
        odds = r["away_ml"]
        won = r["actual_home_win"] == 0
    else:
        continue

    bets_hc += 1
    bankroll_hc += payout_if_win(odds) if won else -100

print(f"Bets placed: {bets_hc}")
if bets_hc > 0:
    print(f"Profit: ${bankroll_hc:.2f}")
    print(f"Return on money wagered: {(bankroll_hc / (bets_hc * 100)):.1%}")

import random
random.seed(42)  # so results are reproducible when you rerun

print("\n--- Random Baseline (same games, same bet count) ---")

# Same pool of games the model was disagreeing on
candidate_games = [r for r in heavy_fav_games if abs(r["edge"]) > EDGE_THRESHOLD]
sample_size = min(bets_hc, len(candidate_games))  # match the 61 bets from before

random_sample = random.sample(candidate_games, sample_size)

bankroll_rand = 0
for r in random_sample:
    # randomly pick a side, ignoring what the model or edge says
    bet_home = random.choice([True, False])
    if bet_home:
        odds = r["home_ml"]
        won = r["actual_home_win"] == 1
    else:
        odds = r["away_ml"]
        won = r["actual_home_win"] == 0

    bankroll_rand += payout_if_win(odds) if won else -100

print(f"Bets placed: {sample_size}")
print(f"Profit: ${bankroll_rand:.2f}")
print(f"Return on money wagered: {(bankroll_rand / (sample_size * 100)):.1%}")

print("\n--- Random Baseline Distribution (1000 trials) ---")

trial_returns = []
for _ in range(1000):
    sample = random.sample(candidate_games, sample_size)
    bankroll_trial = 0
    for r in sample:
        bet_home = random.choice([True, False])
        if bet_home:
            odds = r["home_ml"]
            won = r["actual_home_win"] == 1
        else:
            odds = r["away_ml"]
            won = r["actual_home_win"] == 0
        bankroll_trial += payout_if_win(odds) if won else -100
    trial_returns.append(bankroll_trial / (sample_size * 100))

trial_returns.sort()
n = len(trial_returns)
avg_return = sum(trial_returns) / n

print(f"Average random return across 1000 trials: {avg_return:.1%}")
print(f"Worst 5% of trials landed below: {trial_returns[int(n * 0.05)]:.1%}")
print(f"Best 5% of trials landed above: {trial_returns[int(n * 0.95)]:.1%}")
print(f"Your model's actual return on this same pool: -18.2%")
