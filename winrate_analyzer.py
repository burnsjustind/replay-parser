import argparse
import glob
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class GameRecord:
    source_file: str
    best_of_3_id: str | None
    best_of_3_game_number: int | None
    did_win: bool
    self_team: list[str]
    opponent_team: list[str]
    self_leads: list[str]
    self_back: list[str]
    self_tera: str | None


def _to_rate(wins: int, total: int) -> dict[str, Any]:
    losses = total - wins
    winrate = round(wins / total, 4) if total else None
    return {"wins": wins, "losses": losses, "total": total, "winrate": winrate}


def _identify_sides(game: dict[str, Any], target_player: str) -> tuple[dict[str, Any], dict[str, Any], bool] | None:
    p1 = game.get("player1", {})
    p2 = game.get("player2", {})
    p1_name = p1.get("username")
    p2_name = p2.get("username")

    if p1_name == target_player:
        did_win = game.get("winning_player") == 1
        return p1, p2, did_win
    if p2_name == target_player:
        did_win = game.get("winning_player") == 2
        return p2, p1, did_win
    return None


def load_games(paths: list[str], target_player: str) -> list[GameRecord]:
    games: list[GameRecord] = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)

        sides = _identify_sides(payload, target_player)
        if not sides:
            continue

        self_side, opponent_side, did_win = sides
        self_team = [member.get("name") for member in self_side.get("team", []) if member.get("name")]
        opponent_team = [
            member.get("name") for member in opponent_side.get("team", []) if member.get("name")
        ]

        games.append(
            GameRecord(
                source_file=path,
                best_of_3_id=payload.get("best_of_3_id"),
                best_of_3_game_number=payload.get("best_of_3_game_number"),
                did_win=did_win,
                self_team=self_team,
                opponent_team=opponent_team,
                self_leads=list(self_side.get("lead_pokemon", [])),
                self_back=list(self_side.get("back_pokemon", [])),
                self_tera=self_side.get("terastalized_pokemon"),
            )
        )
    return games


def compute_overall_game_winrate(games: list[GameRecord]) -> dict[str, Any]:
    wins = sum(1 for g in games if g.did_win)
    return _to_rate(wins, len(games))


def _group_bo3(games: list[GameRecord]) -> dict[str, list[GameRecord]]:
    grouped: dict[str, list[GameRecord]] = defaultdict(list)
    for game in games:
        if game.best_of_3_id:
            grouped[game.best_of_3_id].append(game)
    return grouped


def _bo3_winner(games_in_match: list[GameRecord]) -> bool | None:
    wins = sum(1 for g in games_in_match if g.did_win)
    losses = len(games_in_match) - wins
    if wins > losses:
        return True
    if losses > wins:
        return False
    return None


def compute_overall_bo3_winrate(games: list[GameRecord]) -> dict[str, Any]:
    grouped = _group_bo3(games)
    decided: list[bool] = []
    undecided_count = 0
    for match_games in grouped.values():
        result = _bo3_winner(match_games)
        if result is None:
            undecided_count += 1
            continue
        decided.append(result)

    wins = sum(1 for r in decided if r)
    summary = _to_rate(wins, len(decided))
    summary["undecided_matches"] = undecided_count
    return summary


def compute_bo3_vs_opponent_set_winrate(
    games: list[GameRecord], required_opponent_pokemon: list[str]
) -> dict[str, Any]:
    required = {name.lower() for name in required_opponent_pokemon}
    grouped = _group_bo3(games)

    filtered: list[list[GameRecord]] = []
    for match_games in grouped.values():
        qualifies = any(
            required.issubset({name.lower() for name in game.opponent_team})
            for game in match_games
        )
        if qualifies:
            filtered.append(match_games)

    decided: list[bool] = []
    undecided_count = 0
    for match_games in filtered:
        result = _bo3_winner(match_games)
        if result is None:
            undecided_count += 1
            continue
        decided.append(result)

    wins = sum(1 for r in decided if r)
    summary = _to_rate(wins, len(decided))
    summary["required_opponent_pokemon"] = required_opponent_pokemon
    summary["matching_best_of_3"] = len(filtered)
    summary["undecided_matches"] = undecided_count
    return summary


def compute_game_winrate_by_brought_pokemon(games: list[GameRecord]) -> dict[str, dict[str, Any]]:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"wins": 0, "total": 0})
    for game in games:
        brought = set(game.self_leads + game.self_back)
        for pokemon in brought:
            counts[pokemon]["total"] += 1
            if game.did_win:
                counts[pokemon]["wins"] += 1

    return {
        pokemon: _to_rate(stats["wins"], stats["total"])
        for pokemon, stats in sorted(counts.items())
    }


def compute_game_winrate_by_lead_pair(games: list[GameRecord]) -> dict[str, dict[str, Any]]:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"wins": 0, "total": 0})
    for game in games:
        if not game.self_leads:
            continue
        lead_pair = " + ".join(sorted(game.self_leads))
        counts[lead_pair]["total"] += 1
        if game.did_win:
            counts[lead_pair]["wins"] += 1

    return {
        lead_pair: _to_rate(stats["wins"], stats["total"])
        for lead_pair, stats in sorted(counts.items())
    }


def compute_game_winrate_by_tera(games: list[GameRecord]) -> dict[str, dict[str, Any]]:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"wins": 0, "total": 0})
    for game in games:
        tera_key = game.self_tera if game.self_tera else "No Terastallization"
        counts[tera_key]["total"] += 1
        if game.did_win:
            counts[tera_key]["wins"] += 1

    return {
        tera_target: _to_rate(stats["wins"], stats["total"])
        for tera_target, stats in sorted(counts.items())
    }


def analyze_winrates(
    games: list[GameRecord],
    required_opponent_pokemon: list[str] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "overall_best_of_3_winrate": compute_overall_bo3_winrate(games),
        "overall_individual_game_winrate": compute_overall_game_winrate(games),
        "individual_game_winrate_by_brought_pokemon": compute_game_winrate_by_brought_pokemon(games),
        "individual_game_winrate_by_lead_pair": compute_game_winrate_by_lead_pair(games),
        "individual_game_winrate_by_terastalized_pokemon": compute_game_winrate_by_tera(games),
    }

    if required_opponent_pokemon:
        result["best_of_3_winrate_vs_opponent_pokemon_set"] = compute_bo3_vs_opponent_set_winrate(
            games,
            required_opponent_pokemon,
        )

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute winrate slices from replay_parser.py output JSON files."
    )
    parser.add_argument(
        "--player",
        default="Spurrific",
        help="Username to analyze.",
    )
    parser.add_argument(
        "--input-glob",
        default="*_parsed.json",
        help="Glob pattern for parsed replay JSON files.",
    )
    parser.add_argument(
        "--opponent-pokemon",
        nargs="*",
        default=None,
        help="Optional list (1-6) of opponent Pokemon names for Bo3 filtered winrate.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Optional output path for analysis JSON.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = sorted(glob.glob(args.input_glob))
    games = load_games(paths, args.player)

    analysis = {
        "player": args.player,
        "input_file_count": len(paths),
        "games_used": len(games),
        "metrics": analyze_winrates(games, args.opponent_pokemon),
    }

    output_text = json.dumps(analysis, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(output_text + "\n", encoding="utf-8")
        print(f"Wrote winrate analysis to {output_path}")
    else:
        print(output_text)


if __name__ == "__main__":
    main()
