import random
import player_stats
import defense_pos

MARKET_TO_STAT_KEY = {
    "player_pass_yds": "passing_yards",
    "player_pass_yds_alternate": "passing_yards",
    "player_rush_yds": "rushing_yards",
    "player_rush_yds_alternate": "rushing_yards",
    "player_reception_yds": "receiving_yards",
    "player_reception_yds_alternate": "receiving_yards",
    "player_receptions": "receptions",
}

STAT_KEY_TO_EPA_TYPE = {
    "passing_yards": "receiving",  # defense faces this as receiving/passing yardage allowed
    "rushing_yards": "rushing",
    "receiving_yards": "receiving",
    "receptions": "receiving",
}



def simulate_stat(weighted_samples, num_simulations=10000):
    """
    weighted_samples: list of (value, weight) tuples, like what
    player_profile['_weighted_samples'][stat] returns.
    Returns a list of num_simulations simulated outcomes, drawn
    with replacement according to the real historical weights.
    """

    if not weighted_samples:
        return []

    values = [v for v, w in weighted_samples]
    weights = [w for v, w in weighted_samples]

    return random.choices(values, weights=weights, k=num_simulations)
def probability_over_line(simulated_value, line):
    """What fraction of simulated outcomes clear this line"""
    if not simulated_value:
        return None
    hits = sum(1 for v in simulated_value if v > line)
    return round(hits/len(simulated_value)*100, 1)

def probability_under_line(simulated_value, line):
    if not simulated_value:
        return None
    hits = sum(1 for v in simulated_value if v <line)
    return round(hits/len(simulated_value)*100, 1)

def adjust_for_defense(simulated_values, opponent_epa, league_avg_epa, strength=0.5):
    """
    Scales simulated values based on how this opponent's EPA-allowed
    compares to league average. A positive gap (opponent allows more EPA
    than average = weaker defense) scales values UP; a negative gap
    scales them DOWN.

    strength: 0 to 1, how strongly the defensive signal should move the
    simulation. 0.5 is a moderate, not-overconfident starting point \u2014
    tune this later once we see how it affects real picks.
    """
    if opponent_epa is None or league_avg_epa is None or league_avg_epa == 0:
        return simulated_values  # can't adjust without both numbers

    relative_diff = (opponent_epa - league_avg_epa) / abs(league_avg_epa)
    scale_factor = 1 + (relative_diff * strength)
    scale_factor = max(0.5, min(1.5, scale_factor))  # cap extreme swings

    return [v * scale_factor for v in simulated_values]

MIN_SAMPLES_FOR_SIMULATION = 6

def simulate_pick_probability(player_profile, market, point, side, position_defense_profile, league_avg_cache):
    stat_key = MARKET_TO_STAT_KEY.get(market)
    if stat_key is None or not player_profile:
        return None

    samples = player_profile.get("_weighted_samples", {}).get(stat_key)
    if not samples or len(samples) < MIN_SAMPLES_FOR_SIMULATION:
        return None  # too few real games to trust a simulated distribution

    sim = simulate_stat(samples)

    # Diagnostic: flag any simulation that's suspiciously unanimous
    unique_values = set(v for v, w in samples)
    if len(unique_values) <= 2:
        print(f"[WARNING] Only {len(unique_values)} distinct real values behind this simulation "
              f"({stat_key}, {len(samples)} games) \u2014 result may be artificially certain.")

    epa_type = STAT_KEY_TO_EPA_TYPE.get(stat_key)
    epa_field = f"{epa_type}_epa_allowed_per_game"
    position = player_profile.get("position")

    opponent_epa = None
    if position_defense_profile and position in position_defense_profile:
        opponent_epa = position_defense_profile[position].get(epa_field)

    cache_key = (position, epa_type)
    if cache_key not in league_avg_cache:
        import defense_pos
        league_avg_cache[cache_key] = defense_pos.get_league_average_epa(position, epa_type)
    league_avg = league_avg_cache[cache_key]

    sim = adjust_for_defense(sim, opponent_epa, league_avg)

    if side == "Over":
        result = probability_over_line(sim, point)
    elif side == "Under":
        result = probability_under_line(sim, point)
    else:
        return None

    if result is not None:
        result = max(5.0, min(95.0, result))  # never report false 100%/0% certainty

    return result

