import os
import requests
from datetime import datetime
import anthropic
import math
import nflreadpy as nfl

"""Importing the AI"""
ODDS_API_KEY = os.environ["ODDS_API_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

"""Line to setup connection to claude"""
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

"""Naming the odds conditions for later"""
ODDS_ENDPOINT = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"
favorite_ODDS_CUTOFF = -300
TOP_N = 10
LOOKBACK_GAMES = 5
CURRENT_SEASON = 2026

def american_to_implied_odds(odds):
    if odds < 0:
        return -odds / (-odds + 100)
    else:
        return 100 / (odds + 100)

def remove_vig(odds_a, odds_b):
    prob_a = american_to_implied_odds(odds_a)
    prob_b = american_to_implied_odds(odds_b)
    total = prob_a + prob_b 
    fair_a = prob_a/total
    fair_b = prob_b/total
    return fair_a, fair_b

def margin_to_win_prob(margin_diff):
    k = 0.1
    return 1 / (1 + math.exp(-k * margin_diff))

def calculate_edge(model_prob, fair_market_prob):
    return model_prob - fair_market_prob

Target_book = "Fanduel"
