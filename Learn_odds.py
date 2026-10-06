import os
import csv
import requests
from datetime import datetime
import math
import nflreadpy as nfl
import anthropic 
import sys
import json
import team_stats
import player_stats


"""Imports AI using """
ODDS_API_KEY = os.environ["ODDS_API_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]


client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
PROP_MARKETS = [
    "player_anytime_td",
    "player_tds_over",
    "player_pass_tds",
    "player_pass_yds",
    "player_pass_yds_alternate",
    "player_rush_yds",
    "player_rush_yds_alternate",
    "player_reception_yds",
    "player_reception_yds_alternate",
    "player_receptions",
]

ODDS_ENDPOINT = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"

"""Convert odd to percentages"""
"""Expected value in dollars for a given stake, based on YOUR model's probability."""
def american_to_implied_prob(odds):
    if odds < 0:
        return -odds/ (-odds + 100)
    else:
        return 100/(odds +100)
#print(american_to_implied_prob(-300))
#print(american_to_implied_prob(150))

"""Removes vig for money line(Sportsbook edge)"""
def remove_vig(odds_a, odds_b):
    prob_a = american_to_implied_prob(odds_a)
    prob_b = american_to_implied_prob(odds_b)
    total = prob_a + prob_b
    fair_a = prob_a / total
    fair_b = prob_b / total
    return fair_a, fair_b
"""Removes vig for player props"""
def build_fair_probs_for_player(player_lines):
    fair_lines = []
    pairs = {}       # (market_type, point) -> {"Over": price, "Under": price}
    alt_lines = {}   # market_type -> list of (point, price) for alternates

    for market_type, side, point, price in player_lines:
        if market_type.endswith("_alternate"):
            alt_lines.setdefault(market_type, []).append((side, point, price))
        elif side in ("Over", "Under"):
            key = (market_type, point)
            pairs.setdefault(key, {})[side] = price
        else:
            implied = american_to_implied_prob(price)
            fair_lines.append({
                "market": market_type, "side": side, "point": point,
                "price": price, "fair_prob": round(implied * 100, 1),
            })

    # Primary Over/Under lines - exact vig removal
    vig_ratio_by_stat = {}  # base market name -> measured vig multiplier
    for (market_type, point), sides in pairs.items():
        if "Over" in sides and "Under" in sides:
            raw_over = american_to_implied_prob(sides["Over"])
            raw_under = american_to_implied_prob(sides["Under"])
            total = raw_over + raw_under
            vig_ratio_by_stat[market_type] = total  # store for use on alt lines

            fair_over, fair_under = remove_vig(sides["Over"], sides["Under"])
            fair_lines.append({
                "market": market_type, "side": "Over", "point": point,
                "price": sides["Over"], "fair_prob": round(fair_over * 100, 1),
            })
            fair_lines.append({
                "market": market_type, "side": "Under", "point": point,
                "price": sides["Under"], "fair_prob": round(fair_under * 100, 1),
            })

    # Alternate lines - approximate vig removal using the primary market's measured vig
    for alt_market, entries in alt_lines.items():
        base_market = alt_market.replace("_alternate", "")
        vig_total = vig_ratio_by_stat.get(base_market)

        for side, point, price in entries:
            raw_prob = american_to_implied_prob(price)
            if vig_total:
                adjusted_prob = raw_prob / vig_total
                fair_lines.append({
                    "market": alt_market, "side": side, "point": point,
                    "price": price, "fair_prob": round(adjusted_prob * 100, 1),
                    "note": "vig-adjusted (approximated from primary line)",
                })
            else:
                fair_lines.append({
                    "market": alt_market, "side": side, "point": point,
                    "price": price, "fair_prob": round(raw_prob * 100, 1),
                    "note": "raw probability - no primary line found to calibrate vig",
                })

    return fair_lines


#fair_favorite, fair_underdog = remove_vig(-300, 240)
#print(fair_favorite)
#print(fair_underdog)
#print(fair_favorite + fair_underdog)



def margin_to_win_prob(margin_diff):
    k = 0.1
    return 1 / (1 + math.exp(-k * margin_diff))

#print(margin_to_win_prob(0))
#print(margin_to_win_prob(10))
#print(margin_to_win_prob(-10))

"""Calculate edge"""
def calculate_edge(model_prob, fair_market_prob):
    return model_prob - fair_market_prob

#model_prob = margin_to_win_prob(10)
#edge = calculate_edge(model_prob, fair_favorite)
#print(model_prob)
#print(fair_favorite)
#print(edge)

"""Looking at multiple games"""
#games = [
#{"favorite": "Team A", "underdog": "Team B", "fav_odds": -300, "dog_odds": 240, "margin_diff": 10},
#    {"favorite": "Team C", "underdog": "Team D", "fav_odds": -150, "dog_odds": 130, "margin_diff": 2},
#    {"favorite": "Team E", "underdog": "Team F", "fav_odds": -400, "dog_odds": 320, "margin_diff": -3},
#]


#for game in games:
#    fair_fav, fair_dog = remove_vig(game["fav_odds"], game["dog_odds"])
#    model_prob = margin_to_win_prob(game["margin_diff"])
#    edge = calculate_edge(model_prob, fair_fav)
#    print(game["favorite"], "edge:", edge)



def generate_analysis(favorite, underdog, fair_prob, model_prob, edge):
    prompt = f"""
    Favorite: {favorite}
    Underdog: {underdog}
    Fair market probability: {fair_prob:.1%}
    Model probability: {model_prob:.1%}
    Edge: {edge:.1%}

    In 2 sentences, explain whether this edge is meaningful or negligible,
    based only on these numbers. Be honest if the edge is small.
    """
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


def generate_matchup_analysis(favorite, underdog, fav_profile, dog_profile, fair_prob):
    prompt = f"""
    Matchup: {favorite} (favorite) vs {underdog} (underdog)
    Fair market win probability for {favorite}: {fair_prob:.1%}

    {favorite} stats (per game): {fav_profile}
    {underdog} stats (per game): {dog_profile}

    Based only on these numbers, analyze this matchup: identify each team's
    apparent strengths and weaknesses, and note whether the favorite's stats
    support the market's {fair_prob:.1%} confidence in them, or whether
    something here suggests the market might be over/under-valuing this team.
    Be honest if the stats don't clearly support a strong opinion either way.
    Answer in 4-5 sentences.
    """
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=250,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text
def rank_player_props_with_ai(player_name, fair_lines, player_profile, game_context=""):
    lines_text = "\n".join(
        f"- {l['market']} {l['side']} {l['point']}: fair probability {l['fair_prob']}%"
        for l in fair_lines
    )

    stats_text = player_profile if player_profile else "No recent performance data available for this player."

    prompt = f"""
    Player: {player_name}
    Game context: {game_context if game_context else "No additional context provided."}

    Recent performance (per game averages): {stats_text}

    Prop lines, with vig already removed to show fair probability:
    {lines_text}

    Based on both the player's recent real performance AND the fair
    probabilities above, analyze whether any of these lines look
    mispriced relative to their actual recent output. Be specific about
    which stat categories support or contradict the market's pricing.
    If the player's recent stats don't clearly support a strong opinion,
    say so honestly rather than manufacturing a recommendation.
    Answer in 4-5 sentences.
    """
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=250,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text

def rank_top_value_picks_with_ai(picks, game_context=""):
    picks_text = "\n".join(
        f"- {p['player']}: {p['market']} {p['side']} {p['point']} — "
        f"fair probability {p['fair_prob']}% (odds: {p['price']}) — "
        f"recent performance: {p['player_profile'] if p['player_profile'] else 'no data available'}"
        for p in picks
    )

    prompt = f"""
    Game: {game_context}

    Below are player prop lines at -300 to -200 odds (moderate favorites),
    with vig already removed to show each one's fair probability, alongside
    each player's actual recent per-game performance data.

    {picks_text}

     From this list, select ONLY picks where the player's REAL recent
    performance stats clearly support the line hitting — not just picks
    with a high fair probability. Do not include a pick if the recent
    stats argue against it or fall short of the line. Do not pad the
    list with weak picks just to reach a certain count.

    Start your response with exactly one line stating how many picks
    qualified, in this format: "X of 10 picks are well-supported by
    recent performance data." Then list only the qualifying picks below
    that line, ranked strongest to weakest. For each, state ONLY the
    pick, its fair probability, its odds, and a one-sentence reason
    grounded in the actual stat data. Do not include any section
    discussing picks that didn't qualify — the count on the first line
    is the only place that gets mentioned.
    """
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=700,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text



def fetch_player_props(event_id, market="player_pass_tds"):
    url = f"https://api.the-odds-api.com/v4/sports/americanfootball_nfl/events/{event_id}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": market,
        "oddsFormat": "american",
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()
CACHE_DIR = "cache"

def fetch_player_props_cached(event_id, market="player_pass_tds", force_refresh=False):
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_file = f"{CACHE_DIR}/{event_id}_{market}.json"

    if os.path.exists(cache_file) and not force_refresh:
        print(f"[CACHED] {event_id} - {market}")
        with open(cache_file, "r") as f:
            return json.load(f)

    print(f"[LIVE API CALL] {event_id} - {market}")
    props = fetch_player_props(event_id, market=market)

    with open(cache_file, "w") as f:
        json.dump(props, f)

    return props
def fetch_odds():
    params = {
    "apiKey": ODDS_API_KEY,
    "regions": "us",
    "markets": "h2h",
    "oddsFormat": "american",
}
    resp = requests.get(ODDS_ENDPOINT, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()

"""Fetching real time odds in all categories"""
games = fetch_odds()
for game in games[:2]:
    home_team = game["home_team"]
    away_team = game["away_team"]
    event_id = game["id"]

    fanduel_data = None
    for bookmaker in game["bookmakers"]:
        if bookmaker["key"] == "fanduel":
            fanduel_data = bookmaker
            break

    if fanduel_data is None:
        continue

    outcomes = fanduel_data["markets"][0]["outcomes"]
    odds_by_team = {o["name"]: o["price"] for o in outcomes}
    home_odds = odds_by_team.get(home_team)
    away_odds = odds_by_team.get(away_team)

    if home_odds is None or away_odds is None:
        continue

    favorite, fav_odds = (home_team, home_odds) if home_odds < away_odds else (away_team, away_odds)
    underdog, dog_odds = (away_team, away_odds) if favorite == home_team else (home_team, home_odds)

    fair_fav, fair_dog = remove_vig(fav_odds, dog_odds)

    print(f"\n{favorite} (favorite, {fav_odds}) vs {underdog} ({dog_odds})")
    print(f"  Fair probability: {round(fair_fav*100, 1)}%")

    fav_abbr = team_stats.get_team_abbreviation(favorite)
    dog_abbr = team_stats.get_team_abbreviation(underdog)

    fav_profile = team_stats.get_team_profile(fav_abbr) if fav_abbr else None
    dog_profile = team_stats.get_team_profile(dog_abbr) if dog_abbr else None


    if fav_profile and dog_profile:
        analysis = generate_matchup_analysis(favorite, underdog, fav_profile, dog_profile, fair_fav)
    else:
        analysis = "Team stats unavailable for this matchup."
    print(f"  AI analysis: {analysis}")


    player_lines = {}  # player_name -> list of (market_type, side, price)

    for market_type in PROP_MARKETS:
        props = fetch_player_props_cached(event_id, market=market_type, force_refresh=False)
        if not props.get("bookmakers"):
            continue

        for bookmaker in props["bookmakers"]:
            if bookmaker["key"] != "fanduel":
                continue
            for market in bookmaker["markets"]:
                for outcome in market["outcomes"]:
                    player_name = outcome["description"]
                    side = outcome["name"]          # "Over"/"Under"/"Yes"
                    price = outcome["price"]
                    point = outcome.get("point", "")  # the yardage threshold, if any

                    player_lines.setdefault(player_name, []).append(
                        (market_type, side, point, price)
                    )

    if not player_lines:
        print("No FanDuel prop data available for this game.")
    else:
        all_heavy_favorite_picks = []

        for player_name, lines in player_lines.items():
            fair_lines = build_fair_probs_for_player(lines)
            if not fair_lines:
                continue

            for l in fair_lines:
                if -300 <= l["price"] <= -200:
                    all_heavy_favorite_picks.append({
                        "player": player_name,
                        "market": l["market"],
                        "side": l["side"],
                        "point": l["point"],
                        "price": l["price"],
                        "fair_prob": l["fair_prob"],
                        "player_profile": player_stats.get_player_profile(player_name),
                    })
        all_heavy_favorite_picks.sort(key=lambda p: p["fair_prob"], reverse=True)
        top_candidates = all_heavy_favorite_picks[:15]

        print("\n" + "=" * 50)
        print(f"AI TOP 10 VALUE PICKS ({home_team} vs {away_team})")
        print("=" * 50)
        if top_candidates:
            ai_ranked = rank_top_value_picks_with_ai(top_candidates, game_context=f"{home_team} vs {away_team}")
            print(ai_ranked)
        else:
            print("No props found at -300 odds or shorter for this game.")

    print()

