import nflreadpy as nfl

def check_injury(player_name, season=2026):
    data = nfl.load_injuries([season])
    rows = data.filter(data["full_name"] == player_name).to_dicts()

    if not rows:
        return None

    latest = rows[-1]

    return {
        "status": latest["report_status"],
        "injury": latest["report_primary_injury"],
        "practice": latest["practice_status"],
    }

