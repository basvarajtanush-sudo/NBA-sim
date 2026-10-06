import json

with open("pick_log.jsonl", "r") as f:
    lines = [json.loads(l) for l in f if l.strip()]

print(f"Total entries in file: {len(lines)}\n")
print("Last 10 entries:")
for entry in lines[-10:]:
    print(f"  {entry['player']} — {entry['market']} {entry['side']} {entry['point']} (odds: {entry['price']}, fair_prob: {entry['fair_prob']}%)")