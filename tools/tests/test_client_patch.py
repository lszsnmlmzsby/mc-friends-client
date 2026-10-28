import codecs
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


patch = load('client_patch', ROOT / 'tools/build-client-patch.py')
release = load('build_release', ROOT / 'build-release.py')


class ClientPatchTest(unittest.TestCase):
    def test_patch_only_replaces_three_scripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = patch.build(root / 'patch.zip')
            client = root / 'installed'
            sentinels = {
                'launcher/Plain Craft Launcher 2.exe': b'existing launcher',
                'launcher/PCL/Setup.ini': b'personal launcher settings',
                'launcher/.minecraft/versions/example/mods/existing.jar': b'existing mod',
                'launcher/.minecraft/versions/example/options.txt': b'personal keys',
                'runtime/java.exe': b'existing runtime',
            }
            for relative, data in sentinels.items():
                target = client / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(set(archive.namelist()), set(patch.PATCH_FILES))
                for relative in archive.namelist():
                    data = archive.read(relative)
                    self.assertTrue(data.startswith(codecs.BOM_UTF8))
                    self.assertEqual(data.decode('utf-8-sig'), (ROOT / 'client-source' / relative).read_text(encoding='utf-8-sig'))
                archive.extractall(client)
            for relative, data in sentinels.items():
                self.assertEqual((client / relative).read_bytes(), data)
            with self.assertRaises(FileExistsError):
                patch.build(output)

    def test_full_bundle_defaults_to_notifications_without_auto_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = root / 'launcher/PCL/Setup.ini'
            release.disable_pcl_auto_download(root)
            self.assertEqual(settings.read_text(encoding='utf-8'), 'SystemSystemUpdate:1\n')
            settings.write_text('UiLogoText:original\nSystemSystemUpdate:0\nSystemSystemUpdate:3\n', encoding='utf-8-sig')
            release.disable_pcl_auto_download(root)
            release.disable_pcl_auto_download(root)
            self.assertEqual(settings.read_text(encoding='utf-8'), 'UiLogoText:original\nSystemSystemUpdate:1\n')


if __name__ == '__main__':
    unittest.main()
