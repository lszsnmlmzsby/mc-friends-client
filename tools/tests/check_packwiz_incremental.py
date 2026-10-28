"""Exercise the installed packwiz runtime against a local HTTP fixture."""
import argparse
import functools
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from fool_customizations import BOOK, CONFIG, SCRIPT, retain_book


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check(java, bootstrap, installer):
    with tempfile.TemporaryDirectory(prefix='friendsmc-packwiz-test-') as temporary:
        root = Path(temporary)
        pub, game = root / 'publish', root / 'game'
        pub.mkdir(); game.mkdir()
        files = {
            'mods/unchanged.jar': b'unchanged mod fixture' * 128,
            CONFIG.as_posix(): b'[death_item_retention]\nenabled=true\nitems=["tarotcards:tarot_deck"]\n',
        }

        def publish(version):
            entries = []
            for relative, data in files.items():
                target = pub / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                entries.append(f'[[files]]\nfile={json.dumps(relative)}\nhash="{sha(data)}"\n')
            index = ('hash-format="sha256"\n' + '\n'.join(entries)).encode()
            (pub / 'index.toml').write_bytes(index)
            (pub / 'pack.toml').write_text(
                f'name="Incremental fixture"\nauthor="FriendsMC"\nversion="{version}"\npack-format="packwiz:1.1.0"\n'
                f'[index]\nfile="index.toml"\nhash-format="sha256"\nhash="{sha(index)}"\n'
                '[versions]\nminecraft="1.20.1"\nforge="47.4.12"\n', encoding='utf-8')

        hits = []

        class Handler(SimpleHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path.split('?')[0])
                super().do_GET()

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(pub)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def sync():
            result = subprocess.run([
                str(java), '-Djava.awt.headless=true', '-Dstdout.encoding=UTF-8', '-Dstderr.encoding=UTF-8',
                '-jar', str(bootstrap), '--bootstrap-no-update', '--bootstrap-main-jar', str(installer),
                '-g', '-s', 'client', f'http://127.0.0.1:{server.server_port}/pack.toml',
            ], cwd=game, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=45)
            if result.returncode:
                raise AssertionError(result.stdout + result.stderr)

        try:
            publish('test-1'); sync()
            old_mod = game / 'mods/unchanged.jar'
            old_bytes, old_mtime = old_mod.read_bytes(), old_mod.stat().st_mtime_ns
            personal = game / 'options.txt'
            personal.write_bytes(b'personal settings')
            extra = game / 'mods/personal.jar'
            extra.write_bytes(b'personal mod')

            files[CONFIG.as_posix()] = retain_book(files[CONFIG.as_posix()].decode()).encode()
            files[SCRIPT.as_posix()] = (ROOT / 'packs/fool/overrides' / SCRIPT).read_bytes()
            publish('test-2'); hits.clear(); sync()
            assert '/mods/unchanged.jar' not in hits, hits
            assert old_mod.read_bytes() == old_bytes and old_mod.stat().st_mtime_ns == old_mtime
            for relative in (CONFIG.as_posix(), SCRIPT.as_posix()):
                assert (game / relative).read_bytes() == files[relative]
                assert '/' + relative in hits, hits
            assert BOOK.encode() in (game / CONFIG).read_bytes()
            assert personal.read_bytes() == b'personal settings'
            assert extra.read_bytes() == b'personal mod'

            hits.clear(); sync()
            assert not any('/' + relative in hits for relative in files), hits
            print('PASS: real packwiz fetched only the changed config and added script; existing mod untouched; personal files retained; repeat sync fetched no payload files.')
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--java', type=Path, required=True)
    parser.add_argument('--bootstrap', type=Path, required=True)
    parser.add_argument('--installer', type=Path, required=True)
    args = parser.parse_args()
    check(args.java.resolve(), args.bootstrap.resolve(), args.installer.resolve())
