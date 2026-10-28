"""Build a scripts-only PCL protection patch for the existing Windows client."""
import argparse
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PATCH_FILES = (
    'scripts/Common.ps1',
    'scripts/Start.ps1',
    'scripts/Start-Fool.ps1',
)


def build(output, source=ROOT / 'client-source'):
    payload = {}
    for relative in PATCH_FILES:
        # Windows PowerShell 5 requires a BOM for Chinese source text.
        payload[relative] = (source / relative).read_text(encoding='utf-8-sig').encode('utf-8-sig')
    output.parent.mkdir(parents=True, exist_ok=True)
    # An explicit allowlist excludes the launcher, account settings, Java and game.
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED) as archive:
        for relative, data in payload.items():
            archive.writestr(relative, data)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/FriendsMC-PCL-Protection-Update.zip')
    args = parser.parse_args()
    output = build(args.output)
    print(f'{output.resolve()} ({output.stat().st_size} bytes)')
