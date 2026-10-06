import json
import nflreadpy as nfl
import pick_tester

LOG_FILE = "pick_log.jsonl"

STAT_FIELD_MAP = {
    "player_pass_yds": "passing_yards",
    "player_pass_yds_alternate": "passing_yards",
    "player_rush_yds": "rushing_yards",
    "player_rush_yds_alternate": "rushing_yards",
    "player_reception_yds": "receiving_yards",
    "player_reception_yds_alternate": "receiving_yards",
    "player_receptions": "receptions",
    "player_pass_completions": "completions",
    "player_pass_attempts": "attempts",
    "player_rush_attempts": "carries",
    "player_pass_tds": "passing_tds",
}

def get_actual_stat(row, market):
    if market == "player_anytime_td":
        total_tds = (row.get("rushing_tds") or 0) + (row.get("receiving_tds") or 0) + (row.get("passing_tds") or 0)
        return total_tds
    if market == "player_rush_reception_yds":
        return (row.get("rushing_yards") or 0) + (row.get("receiving_yards") or 0)
    field = STAT_FIELD_MAP.get(market)
    if field:
        return row.get(field) or 0
    return None

def grade_entry(entry, row):
    actual = get_actual_stat(row, entry["market"])
    if actual is None:
        return None  # unknown market, can't grade

    if entry["market"] == "player_anytime_td" and entry["side"] == "Yes":
        return "hit" if actual >= entry["point"] else "miss"
    if entry["side"] == "Over":
        return "hit" if actual > entry["point"] else "miss"
    if entry["side"] == "Under":
        return "hit" if actual < entry["point"] else "miss"
    return None

def grade_all(season=2026, dry_run=True):
    with open(LOG_FILE, "r") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    stats = nfl.load_player_stats([season]).to_dicts()
    stats_by_player = {}
    for row in stats:
        stats_by_player.setdefault(row["player_display_name"], []).append(row)

    changes = []
    for e in entries:
        if e["result"] is not None:
            continue
        rows = stats_by_player.get(e["player"])
        if not rows:
            changes.append((e, "SKIPPED - no stats found for this player yet"))
            continue
        latest = rows[-1]
        result = grade_entry(e, latest)
        if result is None:
            changes.append((e, "SKIPPED - unrecognized market type"))
            continue
        changes.append((e, result))

    print(f"\n{'DRY RUN - ' if dry_run else ''}Grading results:")
    for e, result in changes:
        print(f"  {e['player']} — {e['market']} {e['side']} {e['point']}: {result}")

    if not dry_run:
        for e, result in changes:
            if result in ("hit", "miss"):
                e["result"] = result
        with open(LOG_FILE, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        print(f"\nSaved {sum(1 for _,r in changes if r in ('hit','miss'))} graded results to {LOG_FILE}")

grade_all(dry_run=False)
pick_tester.check_simulation_calibration()