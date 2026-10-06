import os

if not os.path.exists("pick_log.jsonl"):
    print("File does not exist \u2014 nothing has been logged yet.")
else:
    with open("pick_log.jsonl", "r") as f:
        lines = [line for line in f if line.strip()]
    print(f"{len(lines)} picks logged so far.")
    if lines:
        print("Most recent entry:")
        print(lines[-1])