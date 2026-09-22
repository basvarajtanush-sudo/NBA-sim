import os
import csv
import requests
from datetime import datetime
import math
import nflreadpy as nfl
import anthropic 


"""Imports AI using """
ODDS_API_KEY = os.environ["ODDS_API_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


"""Convert odd to percentages"""
"""Expected value in dollars for a given stake, based on YOUR model's probability."""
def american_to_implied_prob(odds):
    if odds < 0:
        return -odds/ (-odds + 100)
    else:
        return 100/(odds +100)
print(american_to_implied_prob(-300))
print(american_to_implied_prob(150))

"""Removes vig(Sportsbook edge)"""
def remove_vig(odds_a, odds_b):
    prob_a = american_to_implied_prob(odds_a)
    prob_b = american_to_implied_prob(odds_b)
    total = prob_a + prob_b
    fair_a = prob_a / total
    fair_b = prob_b / total
    return fair_a, fair_b

fair_favorite, fair_underdog = remove_vig(-300, 240)
print(fair_favorite)
print(fair_underdog)
print(fair_favorite + fair_underdog)



def margin_to_win_prob(margin_diff):
    k = 0.1
    return 1 / (1 + math.exp(-k * margin_diff))

print(margin_to_win_prob(0))
print(margin_to_win_prob(10))
print(margin_to_win_prob(-10))

"""Calculate edge"""
def calculate_edge(model_prob, fair_market_prob):
    return model_prob - fair_market_prob

model_prob = margin_to_win_prob(10)
edge = calculate_edge(model_prob, fair_favorite)
print(model_prob)
print(fair_favorite)
print(edge)

"""Looking at multiple games"""
games = [
{"favorite": "Team A", "underdog": "Team B", "fav_odds": -300, "dog_odds": 240, "margin_diff": 10},
    {"favorite": "Team C", "underdog": "Team D", "fav_odds": -150, "dog_odds": 130, "margin_diff": 2},
    {"favorite": "Team E", "underdog": "Team F", "fav_odds": -400, "dog_odds": 320, "margin_diff": -3},
]


for game in games:
    fair_fav, fair_dog = remove_vig(game["fav_odds"], game["dog_odds"])
    model_prob = margin_to_win_prob(game["margin_diff"])
    edge = calculate_edge(model_prob, fair_fav)
    print(game["favorite"], "edge:", edge)



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
result = generate_analysis("Team A", "Team B", fair_favorite, model_prob, edge)
print(result)

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

games = fetch_odds()
for g in games:
    print(game[id], g[home, team], "vs", g["away_team"])