import argparse
import json
import re
from dataclasses import dataclass
#python replay_parser.py "Gen9VGC2026RegFBo3-2026-02-07-jagsamurott-spurrific.html" -o parsed_output.json


@dataclass
class TeamPokemon:
    name: str
    item: str | None
    ability: str | None
    moves: list[str]
    tera_type: str | None


def _extract_player(slot: str) -> str:
    side = slot.split(":", 1)[0].strip()
    if side.startswith("p1"):
        return "p1"
    if side.startswith("p2"):
        return "p2"
    return side


def _extract_species_from_details(details: str) -> str:
    return details.split(",", 1)[0].strip()


def _normalize_species(species: str) -> str:
    if species.endswith("-Tera"):
        return species[: -len("-Tera")]
    return species


def _extract_nickname(slot: str) -> str | None:
    if ":" not in slot:
        return None
    return slot.split(":", 1)[1].strip()


def _parse_showteam(raw: str) -> list[dict]:
    team: list[dict] = []
    for member_raw in raw.split("]"):
        member_raw = member_raw.strip()
        if not member_raw:
            continue
        fields = member_raw.split("|")
        if len(fields) < 6:
            continue

        name = fields[0].strip()
        item = fields[2].strip() or None
        ability = fields[3].strip() or None
        moves_field = fields[4].strip()
        tera_type_raw = fields[-1].strip()
        tera_type = tera_type_raw.lstrip(",") or None
        moves = [m.strip() for m in moves_field.split(",") if m.strip()]

        team.append(
            TeamPokemon(
                name=name,
                item=item,
                ability=ability,
                moves=moves,
                tera_type=tera_type,
            ).__dict__
        )
    return team


def parse_replay_log(log_text: str) -> dict:
    p1_username = None
    p2_username = None
    p1_team = []
    p2_team = []
    p1_leads: list[str] = []
    p2_leads: list[str] = []
    p1_back: list[str] = []
    p2_back: list[str] = []
    p1_tera: str | None = None
    p2_tera: str | None = None
    winner: int | None = None
    best_of_3_id: str | None = None
    best_of_3_game_number: int | None = None
    nickname_to_species = {"p1": {}, "p2": {}}

    for line in log_text.splitlines():
        line = line.strip()
        if not line or not line.startswith("|"):
            continue

        parts = line.split("|")
        if len(parts) < 2:
            continue
        event = parts[1]

        if event == "player" and len(parts) >= 5:
            slot = parts[2].strip()
            username = parts[3].strip()
            if not username:
                continue
            if slot == "p1":
                p1_username = username
            elif slot == "p2":
                p2_username = username

        elif event == "uhtml" and len(parts) >= 4:
            block_id = parts[2].strip()
            if block_id != "bestof":
                continue

            html = "|".join(parts[3:])
            game_match = re.search(r"Game\s+(\d+)", html)
            if game_match:
                best_of_3_game_number = int(game_match.group(1))

            id_match = re.search(
                r'href="\\?/game-bestof3-([^"]*?-\d+)(?:-[^"/]+)?"',
                html,
            )
            if id_match:
                best_of_3_id = id_match.group(1)

        elif event == "showteam" and len(parts) >= 4:
            slot = parts[2].strip()
            payload = "|".join(parts[3:])
            parsed_team = _parse_showteam(payload)
            if slot == "p1":
                p1_team = parsed_team
            elif slot == "p2":
                p2_team = parsed_team

        elif event == "switch" and len(parts) >= 4:
            slot = parts[2].strip()
            details = parts[3].strip()
            species = _normalize_species(_extract_species_from_details(details))
            player = _extract_player(slot)
            nickname = _extract_nickname(slot)
            if nickname and player in nickname_to_species:
                nickname_to_species[player][nickname] = species
            if player == "p1":
                if species not in p1_leads and len(p1_leads) < 2:
                    p1_leads.append(species)
                elif species not in p1_leads and species not in p1_back:
                    p1_back.append(species)
            elif player == "p2":
                if species not in p2_leads and len(p2_leads) < 2:
                    p2_leads.append(species)
                elif species not in p2_leads and species not in p2_back:
                    p2_back.append(species)

        elif event == "detailschange" and len(parts) >= 4:
            slot = parts[2].strip()
            details = parts[3].strip()
            species = _normalize_species(_extract_species_from_details(details))
            player = _extract_player(slot)
            nickname = _extract_nickname(slot)
            if nickname and player in nickname_to_species:
                nickname_to_species[player][nickname] = species

        elif event == "-terastallize" and len(parts) >= 3:
            slot = parts[2].strip()
            nickname = _extract_nickname(slot)
            player = _extract_player(slot)
            species = nickname_to_species.get(player, {}).get(nickname or "", nickname)
            if player == "p1":
                p1_tera = species
            elif player == "p2":
                p2_tera = species

        elif event == "win" and len(parts) >= 3:
            winner_name = parts[2].strip()
            if p1_username and winner_name == p1_username:
                winner = 1
            elif p2_username and winner_name == p2_username:
                winner = 2

    return {
        "best_of_3_id": best_of_3_id,
        "best_of_3_game_number": best_of_3_game_number,
        "player1": {
            "username": p1_username,
            "team": p1_team,
            "lead_pokemon": p1_leads,
            "back_pokemon": p1_back,
            "terastalized_pokemon": p1_tera,
        },
        "player2": {
            "username": p2_username,
            "team": p2_team,
            "lead_pokemon": p2_leads,
            "back_pokemon": p2_back,
            "terastalized_pokemon": p2_tera,
        },
        "winning_player": winner,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse a Pokemon Showdown replay log into structured JSON."
    )
    parser.add_argument(
        "logfile",
        help="Path to a .log text file containing the replay protocol.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Path to write parsed JSON output.",
    )
    args = parser.parse_args()

    with open(args.logfile, encoding="utf-8") as f:
        log_text = f.read()

    result = parse_replay_log(log_text)
    output_json = json.dumps(result, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json + "\n")
        print(f"Wrote parsed replay JSON to {args.output}")
    else:
        print(output_json)


if __name__ == "__main__":
    main()
