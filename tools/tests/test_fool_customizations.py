import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from fool_customizations import BOOK, CONFIG, SCRIPT, build_server_patch, retain_book

spec = importlib.util.spec_from_file_location("import_fool", TOOLS / "import-fool.py")
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)

UPSTREAM = '''# Preserve this comment and all other rules.
[death_item_retention]
enabled = false # server preference, enabled by the book rule
items = [
  "tarotcards:tarot_deck",
  "tarotcards:the_fool", # upstream item
]

[other]
enabled = false
items = ["minecraft:diamond"]
'''


class FoolCustomizationsTest(unittest.TestCase):
    def test_retention_preserves_other_rules_and_is_idempotent(self):
        result = retain_book(UPSTREAM)
        parsed = tomllib.loads(result)
        self.assertEqual(parsed["death_item_retention"], {
            "enabled": True,
            "items": ["tarotcards:tarot_deck", "tarotcards:the_fool", BOOK],
        })
        self.assertEqual(parsed["other"], tomllib.loads(UPSTREAM)["other"])
        self.assertIn("# Preserve this comment", result)
        self.assertEqual(retain_book(result), result)

    def test_incompatible_upstream_fails(self):
        for text in ("[other]\nitems=[]\n", '[death_item_retention]\nenabled=true\nitems="bad"\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                retain_book(text)

    def test_section_header_comment_is_supported(self):
        text = UPSTREAM.replace("[death_item_retention]", "[death_item_retention] # server rule")
        self.assertIn(BOOK, tomllib.loads(retain_book(text))["death_item_retention"]["items"])

    def test_missing_current_upstream_config_cannot_use_stale_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output = root / "upstream", root / "build"
            (source / "overrides").mkdir(parents=True)
            (source / "modrinth.index.json").write_text(json.dumps({
                "dependencies": {"minecraft": "1.20.1", "forge": "47.4.12"}, "files": [],
            }), encoding="utf-8")
            stale = output / "game" / CONFIG
            stale.parent.mkdir(parents=True)
            stale.write_text(UPSTREAM, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Upstream pack is missing"):
                importer.build(source, root / "server", output, "test-book")

    def test_patch_is_two_files_and_never_edits_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "server"
            config = source / CONFIG
            config.parent.mkdir(parents=True)
            config.write_text(UPSTREAM, encoding="utf-8")
            output = root / "patch"
            build_server_patch(source, output)
            self.assertEqual(config.read_text(encoding="utf-8"), UPSTREAM)
            self.assertEqual({p.relative_to(output) for p in output.rglob("*") if p.is_file()}, {CONFIG, SCRIPT})
            self.assertIn(BOOK, tomllib.loads((output / CONFIG).read_text(encoding="utf-8"))["death_item_retention"]["items"])
            with self.assertRaises(FileExistsError):
                build_server_patch(source, output)

    def test_import_indexes_customized_files_with_correct_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, server, output = root / "upstream", root / "server", root / "build"
            config = source / "overrides" / CONFIG
            config.parent.mkdir(parents=True)
            config.write_text(UPSTREAM, encoding="utf-8")
            (source / "modrinth.index.json").write_text(json.dumps({
                "dependencies": {"minecraft": "1.20.1", "forge": "47.4.12"}, "files": [],
            }), encoding="utf-8")
            # Reused output must not smuggle stale files into the new inventory.
            stale = output / "game/config/stale.toml"
            stale.parent.mkdir(parents=True)
            stale.write_text("stale=true", encoding="utf-8")
            for _ in range(2):
                importer.build(source, server, output, "test-book")
                pub = output / "mirror/releases/test-book"
                records = json.loads((output / "inventory.json").read_text(encoding="utf-8"))["files"]
                self.assertEqual({x["path"] for x in records}, {CONFIG.as_posix(), SCRIPT.as_posix()})
                index = tomllib.loads((pub / "index.toml").read_text(encoding="utf-8"))
                for record in records:
                    path = pub / record["path"]
                    sha = hashlib.sha256(path.read_bytes()).hexdigest()
                    self.assertEqual(record["sha256"], sha)
                    self.assertEqual(record["size"], path.stat().st_size)
                    entry = next(x for x in index["files"] if x["file"] == record["path"])
                    self.assertEqual(entry["hash"], sha)
                pack = tomllib.loads((pub / "pack.toml").read_text(encoding="utf-8"))
                self.assertEqual(pack["index"]["hash"], hashlib.sha256((pub / "index.toml").read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
