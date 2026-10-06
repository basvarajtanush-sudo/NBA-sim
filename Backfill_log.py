import json

LOG_FILE = "pick_log.jsonl"
BACKFILL_DATE = "2026-09-26"  # confirm this matches the real date

picks = [
    {"game": "Chicago Bears vs Philadelphia Eagles", "player": "D'Andre Swift", "market": "player_anytime_td", "side": "Yes", "point": 0.5, "price": 100, "fair_prob": 50.0, "position": "RB"},
    {"game": "Chicago Bears vs Philadelphia Eagles", "player": "D'Andre Swift", "market": "player_rush_reception_yds", "side": "Over", "point": 79.5, "price": -113, "fair_prob": 50.0, "position": "RB"},
    {"game": "Chicago Bears vs Philadelphia Eagles", "player": "Kyle Monangai", "market": "player_rush_yds", "side": "Over", "point": 38.5, "price": -113, "fair_prob": 50.0, "position": "RB"},
    {"game": "Chicago Bears vs Philadelphia Eagles", "player": "Colston Loveland", "market": "player_reception_yds", "side": "Under", "point": 31.5, "price": -113, "fair_prob": 50.0, "position": "TE"},
    {"game": "Chicago Bears vs Philadelphia Eagles", "player": "DeVonta Smith", "market": "player_reception_yds", "side": "Over", "point": 71.5, "price": -113, "fair_prob": 50.0, "position": "WR"},
    {"game": "Chicago Bears vs Philadelphia Eagles", "player": "Dontayvion Wicks", "market": "player_reception_yds", "side": "Over", "point": 41.5, "price": -113, "fair_prob": 50.0, "position": "WR"},
    {"game": "Chicago Bears vs Philadelphia Eagles", "player": "Kyle Monangai", "market": "player_rush_reception_yds", "side": "Over", "point": 51.5, "price": -113, "fair_prob": 49.8, "position": "RB"},
    {"game": "Chicago Bears vs Philadelphia Eagles", "player": "Jalen Hurts", "market": "player_rush_yds", "side": "Over", "point": 24.5, "price": -113, "fair_prob": 50.0, "position": "QB"},
    {"game": "Chicago Bears vs Philadelphia Eagles", "player": "Luther Burden III", "market": "player_reception_yds", "side": "Over", "point": 37.5, "price": -106, "fair_prob": 48.5, "position": "WR"},
    {"game": "Chicago Bears vs Philadelphia Eagles", "player": "Saquon Barkley", "market": "player_rush_yds", "side": "Under", "point": 72.5, "price": -113, "fair_prob": 50.0, "position": "RB"},
]

with open(LOG_FILE, "a") as f:
    for p in picks:
        entry = {
            "date": BACKFILL_DATE,
            "game": p["game"],
            "player": p["player"],
            "market": p["market"],
            "side": p["side"],
            "point": p["point"],
            "price": p["price"],
            "fair_prob": p["fair_prob"],
            "position": p["position"],
            "low_sample": False,
            "result": None,
        }
        f.write(json.dumps(entry) + "\n")

print(f"Backfilled {len(picks)} picks into {LOG_FILE}")