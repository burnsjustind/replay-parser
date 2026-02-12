import argparse
import json
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
    p1_revealed: set[str] = set()
    p2_revealed: set[str] = set()
    p1_tera: str | None = None
    p2_tera: str | None = None
    winner: int | None = None
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
                p1_revealed.add(species)
            elif player == "p2":
                p2_revealed.add(species)

        elif event == "move" and len(parts) >= 3:
            slot = parts[2].strip()
            player = _extract_player(slot)
            nickname = slot.split(":", 1)[1].strip() if ":" in slot else None
            species = nickname_to_species.get(player, {}).get(nickname or "")
            if species:
                if player == "p1":
                    p1_revealed.add(species)
                elif player == "p2":
                    p2_revealed.add(species)

        elif event == "detailschange" and len(parts) >= 4:
            slot = parts[2].strip()
            details = parts[3].strip()
            species = _normalize_species(_extract_species_from_details(details))
            player = _extract_player(slot)
            nickname = _extract_nickname(slot)
            if nickname and player in nickname_to_species:
                nickname_to_species[player][nickname] = species
            if player == "p1":
                p1_revealed.add(species)
            elif player == "p2":
                p2_revealed.add(species)

        elif event == "-terastallize" and len(parts) >= 3:
            slot = parts[2].strip()
            nickname = _extract_nickname(slot)
            player = _extract_player(slot)
            species = nickname_to_species.get(player, {}).get(nickname or "", nickname)
            if player == "p1":
                p1_tera = species
                if species:
                    p1_revealed.add(species)
            elif player == "p2":
                p2_tera = species
                if species:
                    p2_revealed.add(species)

        elif event == "win" and len(parts) >= 3:
            winner_name = parts[2].strip()
            if p1_username and winner_name == p1_username:
                winner = 1
            elif p2_username and winner_name == p2_username:
                winner = 2

    return {
        "player1": {
            "username": p1_username,
            "team": p1_team,
            "revealed_pokemon": sorted(p1_revealed),
            "terastalized_pokemon": p1_tera,
        },
        "player2": {
            "username": p2_username,
            "team": p2_team,
            "revealed_pokemon": sorted(p2_revealed),
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
    args = parser.parse_args()

    with open(args.logfile, encoding="utf-8") as f:
        log_text = f.read()

    result = parse_replay_log(log_text)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
