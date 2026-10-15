# BettingSIM — NFL (and early NBA) Value Bet Finder

A Python tool that pulls live sportsbook odds, cross-references them against real player/team stats, opponent-specific defense data, and a Monte Carlo simulation, then uses Claude to rank the most statistically supported player prop bets. Includes a logging and grading system to track real-world accuracy over time.

**Important context:** the backtesting work behind this project found that public box-score and EPA data alone do not beat closing sportsbook lines (see `back_test.py` / `back_test_epa.py`). This tool is a research and analysis aid, not a proven profitable system — treat every output as a well-informed hypothesis, not a guarantee.

---

## Setup

Set both API keys as environment variables before running anything (they reset every new terminal session):

```
$env:ODDS_API_KEY = "your key here"
$env:ANTHROPIC_API_KEY = "your key here"
```

Install dependencies:

```
pip install nflreadpy anthropic requests nba_api --break-system-packages
```

---

## Core pipeline files

### `Learn_odds_test.py`
**The main script.** Run this to get tonight's ranked player prop picks.

- Fetches live NFL odds (moneyline, spread, totals) via The Odds API, skipping any game that's already started
- Prompts you interactively for an odds range (e.g. -350 to -150) and side preference (Over/Under/Both)
- Pulls FanDuel player prop lines for every game in range, removes the vig to get fair probabilities
- Builds a candidate list combining market odds, player stats, opponent defense, injury status, and Monte Carlo simulation
- Deduplicates so each player only appears once per underlying stat
- Sends the candidate list to Claude, which ranks up to 10 picks with full reasoning
- Automatically logs every pick to `pick_log.jsonl` and flags if too many picks depend on the same opponent's defense

**Run it:**
```
python Learn_odds_test.py
```

### `player_stats.py`
Builds a blended, recency-weighted player profile: combines current and prior season stats, with extra weight for home/away games matching the upcoming matchup. Also computes `target_share_pct` and `air_yards_share_pct` as usage signals. Exposes raw per-game values (`_weighted_samples`) for the Monte Carlo simulation to resample from.

### `team_stats.py`
Team-wide stats and team name → abbreviation lookups (`get_team_profile()`, `get_team_abbreviation()`).

### `defense_pos.py` *(imported as `position_defense`)*
Position-specific defense data: yards and receptions allowed by position (WR/RB/TE/QB), plus EPA-allowed per position (`get_defense_vs_position()`), league-average EPA baselines (`get_league_average_epa()`), and a team-wide pass defense EPA metric for QB props specifically (`get_pass_defense_epa()`).

### `injuries.py`
Checks a player's current injury report status (`check_injury()`). Players listed as "Out" are hard-excluded from candidate picks.

### `monte_carlo.py`
Runs a weighted bootstrap simulation of a player's real game-by-game history, adjusted for opponent defense strength relative to league average. Refuses to simulate on fewer than 6 historical games, and caps every output between 5%–95% to avoid reporting false certainty.

**Important:** real calibration data showed this simulation runs overconfident in the 60–80% probability range. The main pipeline currently treats the market's fair probability as the primary anchor, and only flags large Monte Carlo/market disagreements as a caution signal — not a reason to override the market.

---

## Logging & grading

### `pick_tester.py` *(imported as `pick_logger`)*
- `log_picks()` — writes every AI-selected pick to `pick_log.jsonl`
- `get_track_record()` — prints hit rate by market type, from graded picks
- `check_simulation_calibration()` — compares Monte Carlo and market probability buckets against real hit rates

### `grade_picks.py`
Run this after games finish to fill in real hit/miss results.

```
python grade_picks.py
```

- Only grades a pick once its game actually has a final score (checked against the real schedule) — prevents accidentally grading against a different, unrelated game
- Prints the full track record and calibration check after grading

### `pick_log.jsonl`
The actual log file — one JSON entry per line, per logged pick. Can be opened directly in any text editor to inspect individual entries.

---

## NBA build (in progress)

### `nba_player_stats.py`
NBA equivalent of `player_stats.py`. Uses the free `nba_api` library (wraps stats.nba.com) instead of a paid option. Home/away is read directly from the game log's `MATCHUP` field — no separate schedule lookup needed.

### `nba_team_defense.py`
Pulls team-wide defensive rating (points allowed per 100 possessions) for every NBA team, with a `reliable` flag that's `False` until a team has played at least 10 games this season. No position-specific NBA defense data yet — `nba_api` doesn't expose a clean position field the way `nflreadpy` does for the NFL.

---

## Player-lookup chatbot (in progress)

### `player_lookup.py`
A newer, separate interaction mode: instead of scanning every game for top picks, ask about one specific player and get a focused deep-dive.

- `find_player_game()` — matches a player's name to their upcoming game using their team
- Still being built out: pulling that game's specific prop line and running the full analysis on just that one player/market

---

## One-off scripts (used for specific fixes, safe to delete or ignore)
`backfill_log.py`, `check_log.py`, `check_last.py`, `check_bijan.py`, `reset_bad_grades.py`, `check_nba_columns.py`, `nba_team_defense_check.py` — these were built to diagnose or fix specific one-time data issues (missing logs, incorrect grades, confirming API columns). They aren't part of the regular workflow.

---

## Known limitations

- FanDuel doesn't post alternate-line Unders for most prop categories — this is a data-feed limitation, not a bug
- The Monte Carlo simulation's accuracy has not been fully validated against the market's own calibration — keep checking `check_simulation_calibration()` as more picks get graded
- The concentration-risk warning only checks for repeated *opponents*, not repeated *players* — a game with 3+ picks on the same player isn't currently flagged
- College football and full NBA player props are scoped but not yet built
