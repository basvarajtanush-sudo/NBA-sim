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
import injuries
import defense_pos as position_defense
import pick_tester as pick_logger
import monte_carlo


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
    "player_pass_completions",
    "player_pass_attempts",
    "player_rush_yds",
    "player_rush_yds_alternate",
    "player_rush_attempts",
    "player_reception_yds",
    "player_reception_yds_alternate",
    "player_receptions",
    "player_rush_reception_yds",
]

ODDS_ENDPOINT = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"


def american_to_implied_prob(odds):
    if odds < 0:
        return -odds / (-odds + 100)
    else:
        return 100 / (odds + 100)


def remove_vig(odds_a, odds_b):
    prob_a = american_to_implied_prob(odds_a)
    prob_b = american_to_implied_prob(odds_b)
    total = prob_a + prob_b
    fair_a = prob_a / total
    fair_b = prob_b / total
    return fair_a, fair_b

def clean_profile_for_prompt(profile):
    if not profile:
        return "no data available"
    return {k: v for k, v in profile.items() if not k.startswith("_")}


def build_fair_probs_for_player(player_lines):
    fair_lines = []
    pairs = {}
    alt_lines = {}

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

    vig_ratio_by_stat = {}
    for (market_type, point), sides in pairs.items():
        if "Over" in sides and "Under" in sides:
            raw_over = american_to_implied_prob(sides["Over"])
            raw_under = american_to_implied_prob(sides["Under"])
            total = raw_over + raw_under
            vig_ratio_by_stat[market_type] = total

            fair_over, fair_under = remove_vig(sides["Over"], sides["Under"])
            fair_lines.append({
                "market": market_type, "side": "Over", "point": point,
                "price": sides["Over"], "fair_prob": round(fair_over * 100, 1),
            })
            fair_lines.append({
                "market": market_type, "side": "Under", "point": point,
                "price": sides["Under"], "fair_prob": round(fair_under * 100, 1),
            })

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


def margin_to_win_prob(margin_diff):
    k = 0.1
    return 1 / (1 + math.exp(-k * margin_diff))


def calculate_edge(model_prob, fair_market_prob):
    return model_prob - fair_market_prob


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
def deduplicate_candidates(picks):
    """
    Keep only one line per player+stat combination: whichever has the
    larger market-vs-MC gap (if either clears 15 points), else whichever
    has the higher fair probability.
    """
    STAT_GROUPS = {
        "player_pass_yds": "passing_yards", "player_pass_yds_alternate": "passing_yards",
        "player_rush_yds": "rushing_yards", "player_rush_yds_alternate": "rushing_yards",
        "player_reception_yds": "receiving_yards", "player_reception_yds_alternate": "receiving_yards",
        "player_receptions": "receptions", "player_anytime_td": "anytime_td",
        "player_rush_reception_yds": "combo_yards",
    }

    def gap(p):
        if p["simulated_prob"] is None:
            return 0
        return abs(p["simulated_prob"] - p["fair_prob"])

    best_by_key = {}
    for p in picks:
        stat_group = STAT_GROUPS.get(p["market"], p["market"])
        key = (p["player"], stat_group)
        current_best = best_by_key.get(key)
        if current_best is None:
            best_by_key[key] = p
            continue
        p_gap, best_gap = gap(p), gap(current_best)
        if max(p_gap, best_gap) >= 15:
            if p_gap > best_gap:
                best_by_key[key] = p
        else:
            if p["fair_prob"] > current_best["fair_prob"]:
                best_by_key[key] = p

    return list(best_by_key.values())


def rank_top_value_picks_with_ai(picks, game_context=""):
    picks_text = "\n".join(
        f"- {p['player']}: {p['market']} {p['side']} {p['point']} \u2014 "
        f"market fair probability {p['fair_prob']}% (odds: {p['price']}, {p['vig_note']}) \u2014 "
        f"Monte Carlo simulated probability: "
        f"{(str(p['simulated_prob']) + '%') if p['simulated_prob'] is not None else 'not available for this market'} \u2014 "
        f"recent performance: {clean_profile_for_prompt(p['player_profile'])} \u2014 "
        f"opponent's defense vs this player's position specifically: {p['position_defense'] if p['position_defense'] else 'no position-specific data available'} \u2014 "
        f"opponent's overall pass defense EPA allowed per play (for QB passing props specifically): {p['pass_defense_epa'] if p['pass_defense_epa'] is not None else 'not applicable (non-QB prop)'} \u2014 "
        f"injury report: {p['injury_status'] if p['injury_status'] else 'no injury listed'} \u2014 "
        f"data reliability: {'LOW SAMPLE SIZE - fewer than 8 games behind this average' if p['low_sample'] else 'adequate sample size'}"
        for p in picks
    )

    side_note = {
        "over": "Only Over bets are included below.",
        "under": "Only Under bets are included below.",
        "both": "Both Over and Under bets are included below \u2014 judge each on its own merits and do not default to favoring Overs just because they're more common.",
    }[SIDE_PREFERENCE]

    static_instructions = """
    Rank ALL of the picks below from strongest to weakest based on how
    well the player's REAL recent performance stats AND the specific
    matchup against the opponent's defense vs that player's exact
    position support the line hitting. Position-specific defense (e.g.,
    yards allowed to WRs specifically, not the team's overall defense)
    is a much more precise signal than a generic team-wide number \u2014 treat
    it accordingly. A strong recent average facing a weak defense is a stronger
    case than the same average facing a tough defense; factor this in
    explicitly. Also weigh target_share_pct and air_yards_share_pct where
    available \u2014 a high target share or air-yards share signals the
    player's usage trend is real and likely to continue, which is a
    stronger and more forward-looking signal than a yardage average alone.
    A low target share paired with a lucky recent yardage average is a
    weaker case than the raw average might suggest.

    The market's fair probability is your primary, default estimate of
    how likely this line is to hit \u2014 treat it as the anchor, not one
    opinion among equals. The Monte Carlo simulated probability is
    supporting context, not an independent vote: use it to add texture
    to your reasoning (e.g., does the player's real game-by-game
    variance make a close-to-average line feel safer or shakier than the
    market number alone suggests?), not to override the market's number.
    Do NOT treat a large gap between the market and the Monte Carlo
    simulation as a reason to favor the simulation \u2014 real-world results
    tonight showed the Monte Carlo running meaningfully overconfident in
    its 60-80% range, so a big gap is more often a sign the simulation is
    drawing on too little real variety of outcomes than a sign the market
    is wrong. When the two numbers are close, note the agreement as a
    mild positive. When they diverge sharply, say so neutrally and
    explain what in the player's specific game log might account for the
    gap, without concluding the market is mispriced because of it.
    When judging the opponent's defense, prioritize the EPA-allowed figures
    (receiving_epa_allowed_per_game, rushing_epa_allowed_per_game) over
    the raw yards-allowed figures for that same position \u2014 EPA reflects
    true defensive value given down/distance/field position, while raw
    yardage can be inflated or deflated by garbage-time snaps. If the two
    signals disagree (e.g., yards allowed look tight but EPA allowed is
    high), trust the EPA number and say so explicitly in your reasoning.
    If a player's injury report shows "Doubtful" or
    "Questionable," you may still include them, but you must factor
    their health status into both the ranking (rank them lower than an
    equally strong but fully healthy pick) and the reasoning. Separately,
    if a pick is marked "LOW SAMPLE SIZE," you must say so
    explicitly using that exact phrase, and rank it lower than an
    otherwise-equal pick with an adequate sample \u2014 this is a different
    and more serious kind of uncertainty than a normal matchup trade-off
    (like a strong player average facing a tougher-than-usual defense).
    Do not blend these two types of caveats together in your reasoning;
    call out low sample size as its own distinct warning. The candidates
    you'll be given have already been deduplicated \u2014 there is only one
    line per player per underlying stat. Rank them as given.
    Return up to 10 picks, ranked strongest to weakest \u2014 but only include
    picks that are genuinely well-supported. If fewer than 10 picks clear
    that bar (for example, if the remaining candidates are all LOW SAMPLE
    SIZE or show a Monte Carlo/market disagreement that favors excluding
    them), return fewer. Do not pad the list with weak picks just to
    reach 10, and do not discuss or list picks you've excluded \u2014 simply
    return the ones that qualify.
    Keep each pick's reasoning to 2-3 sentences maximum \u2014 be direct and
    avoid restating the same defensive number multiple times within one
    pick's explanation.
    For each pick, the header line must include all three of: the pick,
    its fair probability, AND its odds \u2014 for example:
    "1. Christian Watson \u2014 Reception Yds Over 49.5 (Fair prob: 68.5%, odds: -270)"
    Do not omit the odds from the header under any circumstances.
    After your full ranked list, on its own line, write exactly:
    STRUCTURED_PICKS:
    followed immediately by a JSON array of your 10 picks using this exact
    format, with values taken directly from the data above (not reworded):
    [{"player": "Player Name", "market": "market_key", "side": "Over", "point": 49.5}, ...]
    """

    dynamic_prompt = f"""
    Game: {game_context}

    Below are player prop lines at {ODDS_LOW} to {ODDS_HIGH} odds (moderate favorites).
    {side_note}
    Vig has already been removed to show each one's fair probability, alongside
    each player's actual recent per-game performance data.

    {picks_text}
    """

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4500,
        system=[
            {
                "type": "text",
                "text": static_instructions,
                "cache_control": {"type": "ephemeral"}
            }
        ],
        messages=[{"role": "user", "content": dynamic_prompt}]
    )
    full_text = response.content[0].text

    if "STRUCTURED_PICKS:" in full_text:
        display_text, json_part = full_text.split("STRUCTURED_PICKS:", 1)
        cleaned_json = json_part.strip()
        if cleaned_json.startswith("```"):
            cleaned_json = cleaned_json.strip("`")
            if cleaned_json.lower().startswith("json"):
                cleaned_json = cleaned_json[4:]
            cleaned_json = cleaned_json.strip()
        try:
            chosen = json.loads(cleaned_json)
            matched = [
                p for p in picks
                if any(
                    p["player"] == c.get("player")
                    and p["market"] == c.get("market")
                    and p["side"] == c.get("side")
                    and p["point"] == c.get("point")
                    for c in chosen
                )
            ]
            pick_logger.log_picks(matched, game_context)
            print(f"[LOGGED {len(matched)} picks to pick_log.jsonl]")

            opponent_counts = {}
            for m in matched:
                opp = m.get("opponent_abbr")
                if opp:
                    opponent_counts[opp] = opponent_counts.get(opp, 0) + 1

            concentration_warning = ""
            for opp, count in opponent_counts.items():
                if count >= 4:
                    pct = round(count / len(matched) * 100) if matched else 0
                    concentration_warning += (
                        f"\n\u26a0\ufe0f CONCENTRATION WARNING: {count} of these picks "
                        f"({pct}%) are all betting against {opp}'s defense. "
                        f"If {opp} performs better than expected tonight, these picks "
                        f"are likely to miss together, not independently.\n"
                    )

            display_text = display_text.strip() + concentration_warning
        except Exception as e:
            print(f"[Could not parse structured picks: {e}]")
            print(f"[Raw JSON attempted: {json_part.strip()[:300]}]")
        return display_text.strip()
    else:
        print("[STRUCTURED_PICKS: not found in AI response \u2014 nothing logged this run]")

    return full_text


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


def get_odds_range():
    print("Set the odds range for player prop picks (e.g. -350 to -150).")
    low_input = input("Enter the lower bound (more negative, bigger favorite) [default -350]: ").strip()
    high_input = input("Enter the upper bound (less negative, smaller favorite) [default -150]: ").strip()
    low = int(low_input) if low_input else -350
    high = int(high_input) if high_input else -150
    return low, high


def get_side_preference():
    print("\nWhich side(s) should count as candidate picks?")
    choice = input("Type 'over', 'under', or 'both' [default: both]: ").strip().lower()
    if choice not in ("over", "under", "both"):
        choice = "both"
    return choice


SIDE_PREFERENCE = get_side_preference()
ODDS_LOW, ODDS_HIGH = get_odds_range()


def fetch_player_props_cached(event_id, market="player_pass_tds", force_refresh=True):
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
        "markets": "h2h,spreads,totals",
        "oddsFormat": "american",
    }
    resp = requests.get(ODDS_ENDPOINT, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


games = fetch_odds()
league_avg_cache = {}
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

    home_abbr = team_stats.get_team_abbreviation(home_team)
    away_abbr = team_stats.get_team_abbreviation(away_team)

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

    player_lines = {}

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
                    side = outcome["name"]
                    price = outcome["price"]
                    point = outcome.get("point", "")

                    player_lines.setdefault(player_name, []).append(
                        (market_type, side, point, price)
                    )

    alt_unders_found = sum(
        1 for lines in player_lines.values()
        for market_type, side, point, price in lines
        if market_type.endswith("_alternate") and side == "Under"
    )
    print(f"DEBUG: {alt_unders_found} alternate-Under lines found in this game's data")

    if not player_lines:
        print("No FanDuel prop data available for this game.")
    else:
        all_heavy_favorite_picks = []

        for player_name, lines in player_lines.items():
            fair_lines = build_fair_probs_for_player(lines)
            if not fair_lines:
                continue

            player_profile = player_stats.get_player_profile(player_name)
            player_team = player_profile.get("team") if player_profile else None
            if player_team:
                is_home_game = (player_team == home_abbr)
                player_profile = player_stats.get_player_profile(player_name, upcoming_is_home=is_home_game)

            opponent_abbr = None
            if player_team == home_abbr:
                opponent_abbr = away_abbr
            elif player_team == away_abbr:
                opponent_abbr = home_abbr

            opponent_defense = team_stats.get_team_profile(opponent_abbr) if opponent_abbr else None
            position_matchup = position_defense.get_defense_vs_position(opponent_abbr) if opponent_abbr else None
            player_position = player_profile.get("position") if player_profile else None
            defense_vs_player_position = position_matchup.get(player_position) if position_matchup and player_position else None
            pass_defense_epa = position_defense.get_pass_defense_epa(opponent_abbr) if (opponent_abbr and player_position == "QB") else None

            injury = injuries.check_injury(player_name)
            if injury and injury["status"] == "Out":
                continue

            sample_size = player_profile.get("games_used_in_average", 0) if player_profile else 0

            for l in fair_lines:
                side_matches = (
                    SIDE_PREFERENCE == "both"
                    or l["side"].lower() == SIDE_PREFERENCE
                )
                if ODDS_LOW <= l["price"] <= ODDS_HIGH and side_matches:
                    sim_prob = monte_carlo.simulate_pick_probability(
                        player_profile, l["market"], l["point"], l["side"],
                        position_matchup, league_avg_cache
                    )
                    all_heavy_favorite_picks.append({
                        "player": player_name,
                        "market": l["market"],
                        "side": l["side"],
                        "point": l["point"],
                        "price": l["price"],
                        "fair_prob": l["fair_prob"],
                        "player_profile": player_profile,
                        "opponent_defense": opponent_defense,
                        "position_defense": defense_vs_player_position,
                        "pass_defense_epa": pass_defense_epa,
                        "injury_status": injury,
                        "vig_note": l.get("note", "exact vig removal"),
                        "low_sample": sample_size < 8,
                        "simulated_prob": sim_prob,
                        "opponent_abbr": opponent_abbr,
                    })

        all_heavy_favorite_picks.sort(key=lambda p: p["fair_prob"], reverse=True)
        top_candidates = all_heavy_favorite_picks[:60]
        print(f"DEBUG: {len(all_heavy_favorite_picks)} candidates available before trimming to top 35")

        print("\n" + "=" * 50)
        print(f"AI TOP 10 VALUE PICKS ({home_team} vs {away_team})")
        print("=" * 50)
        top_candidates = deduplicate_candidates(top_candidates)
        if top_candidates:
            ai_ranked = rank_top_value_picks_with_ai(top_candidates, game_context=f"{home_team} vs {away_team}")
            print(ai_ranked)
        else:
            print("No props found for this odds range/side preference in this game.")

    print()