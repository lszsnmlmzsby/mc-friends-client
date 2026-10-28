"""Apply FriendsMC's Fool book rule; can also generate a two-file server patch.

Python 3.11+. No network access; the source game directory is never modified by
the CLI. Use the target server's config to preserve its existing retained items.
"""
import argparse
import json
import re
import shutil
import tomllib
from pathlib import Path

BOOK = "ageofmythology:the_fool_book"
CONFIG = Path("config/ageofmythology/death_keep_items.toml")
SCRIPT = Path("kubejs/server_scripts/friendsmc_fool_book.js")
OVERLAYS = Path(__file__).resolve().parents[1] / "packs/fool/overrides"


def retain_book(text):
    """Preserve upstream items/settings, enable retention and append the book once."""
    before = tomllib.loads(text)
    rule = before.get("death_item_retention", {})
    items = rule.get("items")
    if not isinstance(rule.get("enabled"), bool) or not isinstance(items, list) or not all(isinstance(x, str) for x in items):
        raise ValueError("Unsupported death_keep_items.toml schema; review before deploying")
    items = items if BOOK in items else [*items, BOOK]
    section = re.search(r"(?ms)^\[death_item_retention\][ \t]*(?:\#[^\r\n]*)?\r?\n(.*?)(?=^\[|\Z)", text)
    if section is None:
        raise ValueError("Missing death_item_retention section")
    body, enabled_count = re.subn(r"(?m)^([ \t]*enabled[ \t]*=[ \t]*)(?:true|false)\b", r"\g<1>true", section[1])
    body, items_count = re.subn(
        r"(?ms)^([ \t]*items[ \t]*=[ \t]*)\[.*?\]",
        lambda match: match[1] + json.dumps(items, ensure_ascii=False), body,
    )
    if enabled_count != 1 or items_count != 1:
        raise ValueError("Unsupported retention config layout; review before deploying")
    result = text[:section.start(1)] + body + text[section.end(1):]
    before["death_item_retention"].update(enabled=True, items=items)
    if tomllib.loads(result) != before:
        raise ValueError("Retention patch changed unrelated configuration")
    return result


def apply_customizations(game):
    config = game / CONFIG
    # Validate before copying the script, so incompatible upstreams fail clearly.
    updated = retain_book(config.read_text(encoding="utf-8-sig"))
    script = game / SCRIPT
    script.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OVERLAYS / SCRIPT, script)
    config.write_text(updated, encoding="utf-8")
    return {CONFIG.as_posix(), SCRIPT.as_posix()}


def build_server_patch(source_game, output):
    # Require a fresh output directory; do not accidentally edit a running game.
    updated = retain_book((source_game / CONFIG).read_text(encoding="utf-8-sig"))
    output.mkdir(parents=True, exist_ok=False)
    config = output / CONFIG
    config.parent.mkdir(parents=True)
    config.write_text(updated, encoding="utf-8")
    script = output / SCRIPT
    script.parent.mkdir(parents=True)
    shutil.copy2(OVERLAYS / SCRIPT, script)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-game", type=Path, required=True, help="Target server root or a local copy of its config")
    parser.add_argument("--output", type=Path, required=True, help="New directory for the two-file server patch")
    args = parser.parse_args()
    build_server_patch(args.source_game, args.output)
    print(f"Server patch prepared: {args.output.resolve()}; stop the MC server, back up and copy these two files, then restart.")
