import json
import os
from datetime import date

LOG_FILE = "pick_log.jsonl"

def log_picks(picks, game_context):
    with open(LOG_FILE, "a") as f:
        for p in picks:
            entry = {
                "date": str(date.today()),
                "game": game_context,
                "player": p["player"],
                "market": p["market"],
                "side": p["side"],
                "point": p["point"],
                "price": p["price"],
                "fair_prob": p["fair_prob"],
                "simulated_prob": p.get("simulated_prob"),
                "position": p["player_profile"].get("position") if p["player_profile"] else None,
                "low_sample": p["low_sample"],
                "result": None,
            }
            f.write(json.dumps(entry) + "\n")

def check_simulation_calibration():
    with open(LOG_FILE, "r") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    graded = [
        e for e in entries
        if e["result"] in ("hit", "miss") and e.get("simulated_prob") is not None
    ]

    if not graded:
        print("No graded picks with a simulated_prob yet \u2014 nothing to check.")
        return

    bins = [(0, 30), (30, 40), (40, 50), (50, 60), (60, 70), (70, 80), (80, 90), (90, 100)]
    print(f"\n--- Monte Carlo Calibration Check ({len(graded)} graded picks) ---")
    for lo, hi in bins:
        bucket = [e for e in graded if lo <= e["simulated_prob"] < hi]
        if bucket:
            predicted_avg = sum(e["simulated_prob"] for e in bucket) / len(bucket)
            actual_rate = sum(1 for e in bucket if e["result"] == "hit") / len(bucket) * 100
            print(f"  {lo}-{hi}%: n={len(bucket)}, simulation avg={predicted_avg:.1f}%, actual hit rate={actual_rate:.1f}%")

    # Same comparison for the market's own fair_prob, for a side-by-side reference
    print(f"\n--- Market Fair Probability Calibration (same {len(graded)} picks) ---")
    for lo, hi in bins:
        bucket = [e for e in graded if lo <= e["fair_prob"] < hi]
        if bucket:
            predicted_avg = sum(e["fair_prob"] for e in bucket) / len(bucket)
            actual_rate = sum(1 for e in bucket if e["result"] == "hit") / len(bucket) * 100
            print(f"  {lo}-{hi}%: n={len(bucket)}, market avg={predicted_avg:.1f}%, actual hit rate={actual_rate:.1f}%")

def get_track_record():
    if not os.path.exists(LOG_FILE):
        return "No prior picks logged yet — this is the first tracked run."

    with open(LOG_FILE, "r") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    graded = [e for e in entries if e["result"] in ("hit", "miss")]
    if not graded:
        return "Picks have been logged, but none graded yet."

    by_market = {}
    for e in graded:
        by_market.setdefault(e["market"], []).append(e["result"])

    lines = [f"Track record so far ({len(graded)} graded picks):"]
    for market, results in by_market.items():
        hits = results.count("hit")
        lines.append(f"  {market}: {hits}/{len(results)} hit ({round(100*hits/len(results),1)}%)")
    return "\n".join(lines)

print(get_track_record())
