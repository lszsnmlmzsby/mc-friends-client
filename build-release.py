"""Build the Windows portable client from pinned upstream archives (Python 3.11+)."""
import argparse, hashlib, json, os, shutil, struct, urllib.request, zipfile, subprocess, tarfile, stat, copy, posixpath
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def download(url, dest, sha=None):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        req = urllib.request.Request(url, headers={'User-Agent': 'FriendsMC-release-builder'})
        with urllib.request.urlopen(req, timeout=120) as response, dest.open('wb') as output:
            shutil.copyfileobj(response, output)
    if sha and hashlib.sha256(dest.read_bytes()).hexdigest() != sha:
        raise RuntimeError(f'Checksum mismatch: {dest.name}')

def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')

def disable_pcl_auto_download(client):
    settings = client/'launcher/PCL/Setup.ini'
    lines = settings.read_text(encoding='utf-8-sig').splitlines() if settings.exists() else []
    lines = [line for line in lines if not line.startswith('SystemSystemUpdate:')]
    write(settings, '\n'.join([*lines, 'SystemSystemUpdate:1', '']))

def build(cache, destination):
    if destination.exists():
        raise RuntimeError('Output directory already exists; use a fresh directory.')
    sources = json.loads((ROOT/'client-source/THIRD-PARTY.json').read_text(encoding='utf-8-sig'))
    files = [
        ('pcl-2.13.1.1.zip', sources['PCL']['url'], sources['PCL']['sha256'], 'launcher'),
        ('java.zip', sources['Zulu Java']['url'], sources['Zulu Java']['sha256'], 'runtime'),
        ('packwiz-installer.jar', 'https://github.com/packwiz/packwiz-installer/releases/download/v0.5.14/packwiz-installer.jar', sources['packwiz-installer']['sha256'], None),
        ('packwiz-installer-bootstrap.jar', 'https://github.com/packwiz/packwiz-installer-bootstrap/releases/download/v0.0.3/packwiz-installer-bootstrap.jar', sources['packwiz-installer-bootstrap']['sha256'], None),
    ]
    client = destination/'FriendsMC'
    shutil.copytree(ROOT/'client-source', client, ignore=shutil.ignore_patterns('state', 'logs', 'accounts.json', '*.log'))
    # Windows PowerShell 5 reads BOM-less UTF-8 as the system ANSI code page.
    # Normalize packaged scripts so Chinese text cannot alter tokenization.
    for script in client.rglob('*.ps1'):
        script.write_text(script.read_text(encoding='utf-8-sig'), encoding='utf-8-sig')
    shutil.copy2(ROOT/'download-sources.json',client/'download-sources.json')
    shutil.copy2(ROOT/'MOD-CREDITS.md',client/'MOD-CREDITS.md')
    shutil.copytree(ROOT/'mirror-licenses',client/'licenses/mods')
    for name,url,sha,folder in files:
        archive = cache/name
        download(url,archive,sha)
        if folder:
            target = (client/folder).resolve()
            with zipfile.ZipFile(archive) as z:
                for member in z.infolist():
                    if not (target/member.filename).resolve().is_relative_to(target):
                        raise RuntimeError('Unsafe ZIP member')
                z.extractall(target)
        else:
            (client/'tools').mkdir(exist_ok=True)
            shutil.copy2(archive,client/'tools'/name)
    if hashlib.sha256((client/'launcher/Plain Craft Launcher 2.exe').read_bytes()).hexdigest() != sources['PCL']['exeSha256']:
        raise RuntimeError('Unexpected PCL executable in official archive')
    disable_pcl_auto_download(client)
    def nbtstr(s):
        b=s.encode(); return struct.pack('>H',len(b))+b
    data=b'\x0a\x00\x00\x09'+nbtstr('servers')+b'\x0a'+struct.pack('>i',1)
    for name,value in [('name','Friends Minecraft'),('ip','wze.rainplay.cn:21250')]:
        data+=b'\x08'+nbtstr(name)+nbtstr(value)
    (client/'templates').mkdir(exist_ok=True)
    (client/'templates/servers.dat').write_bytes(data+b'\x00\x00')
    license_urls={
        'PCL-LICENCE':'https://raw.githubusercontent.com/Meloong-Git/PCL/0ce35fe7e5cb939500ef754ff177b082927374ad/LICENCE',
        'packwiz-installer-LICENSE':'https://raw.githubusercontent.com/packwiz/packwiz-installer/v0.5.14/LICENSE',
        'packwiz-bootstrap-LICENSE':'https://raw.githubusercontent.com/packwiz/packwiz-installer-bootstrap/v0.0.3/LICENSE',
    }
    for name,url in license_urls.items():
        download(url,client/'licenses'/name)
    shutil.copy2(ROOT/'PLAYER-GUIDE.md',client/'使用说明.md')
    classes=destination/'updater-classes'
    classes.mkdir()
    subprocess.run(['javac','--release','17','-encoding','UTF-8','-d',str(classes),str(ROOT/'updater/FriendsUpdater.java'),str(ROOT/'updater/FoolUpdater.java')],check=True)
    updater=client/'tools/friends-updater.jar'
    for classname, filename in [('FriendsUpdater','friends-updater.jar'),('FoolUpdater','fool-updater.jar')]:
        with zipfile.ZipFile(client/'tools'/filename,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('META-INF/MANIFEST.MF','Manifest-Version: 1.0\nMain-Class: '+classname+'\n\n')
            for p in classes.glob(classname+'*.class'):z.write(p,p.name)
    archive=destination/'FriendsMC-Windows-x64.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        for p in sorted(client.rglob('*')):
            if p.is_file(): z.write(p,p.relative_to(destination))
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    patch=destination/'FriendsMC-UI-Update.zip'
    with zipfile.ZipFile(patch,'w',zipfile.ZIP_DEFLATED) as z:
        z.write(ROOT/'client-source/Start.cmd','Start.cmd')
        for p in sorted((client/'scripts').glob('*.ps1')):
            z.write(p,'scripts/'+p.name)
        z.write(updater,'tools/friends-updater.jar')
        z.write(client/'tools/fool-updater.jar','tools/fool-updater.jar')
        z.write(ROOT/'download-sources.json','download-sources.json')
        z.write(ROOT/'MOD-CREDITS.md','MOD-CREDITS.md')
        for p in (ROOT/'mirror-licenses').glob('*'):
            if p.is_file(): z.write(p,'licenses/mods/'+p.name)
        z.write(ROOT/'UI-UPDATE.md','更新说明.md')
    patch_digest=hashlib.sha256(patch.read_bytes()).hexdigest()
    sums=digest+'  '+archive.name+'\n'+patch_digest+'  '+patch.name+'\n'
    mac=json.loads((ROOT/'mac-source/sources.json').read_text())
    for architecture,key in [('arm64','arm'),('x64','x86')]:
        output=destination/f'FriendsMC-macOS-{architecture}.zip'
        for src in [mac['prism'],mac[key]]:download(src['url'],cache/src['filename'],src['sha256'])
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=5) as z:
            def add(name,data,mode=0o100644):
                info=zipfile.ZipInfo('FriendsMC/'+name);info.create_system=3;info.external_attr=mode<<16;info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,data)
            add('Start.command',(ROOT/'mac-source/Start.command').read_bytes(),0o100755)
            add('tools/friends-updater.jar',updater.read_bytes())
            add('tools/fool-updater.jar',(client/'tools/fool-updater.jar').read_bytes())
            add('tools/packwiz-installer.jar',(client/'tools/packwiz-installer.jar').read_bytes())
            add('tools/packwiz-installer-bootstrap.jar',(client/'tools/packwiz-installer-bootstrap.jar').read_bytes())
            add('download-sources.json',(ROOT/'download-sources.json').read_bytes())
            add('MOD-CREDITS.md',(ROOT/'MOD-CREDITS.md').read_bytes())
            for p in (ROOT/'mirror-licenses').glob('*'):
                if p.is_file(): add('licenses/mods/'+p.name,p.read_bytes())
            add('templates/servers.dat',(client/'templates/servers.dat').read_bytes())
            add('使用说明.md',(ROOT/'MAC-GUIDE.md').read_bytes())
            add('THIRD-PARTY.json',json.dumps(mac,indent=2).encode())
            with zipfile.ZipFile(cache/mac['prism']['filename']) as src:
                for member in src.infolist():
                    if not member.filename.startswith('Prism Launcher.app/'):continue
                    assert '..' not in Path(member.filename).parts
                    info=copy.copy(member);info.filename='FriendsMC/launcher/'+member.filename
                    z.writestr(info,src.read(member))
            with tarfile.open(cache/mac[key]['filename']) as src:
                for member in src.getmembers():
                    parts=member.name.split('/',1)
                    if len(parts)<2:continue
                    relative=parts[1];assert not relative.startswith('/') and '..' not in Path(relative).parts
                    name='runtime/'+relative
                    if member.isfile():add(name,src.extractfile(member).read(),stat.S_IFREG|member.mode)
                    elif member.issym():
                        target=posixpath.normpath(posixpath.join(posixpath.dirname(name),member.linkname))
                        assert target.startswith('runtime/') and not member.linkname.startswith('/')
                        add(name,member.linkname.encode(),stat.S_IFLNK|0o777)
                    elif member.isdir():add(name.rstrip('/')+'/',b'',stat.S_IFDIR|member.mode)
                    else:raise RuntimeError('Unexpected Java archive entry: '+member.name)
            add('licenses/Prism-COPYING.md',urllib.request.urlopen('https://raw.githubusercontent.com/PrismLauncher/PrismLauncher/11.1.1/COPYING.md').read())
            add('licenses/SOURCE-LINKS.txt',b'Prism Launcher source: https://github.com/PrismLauncher/PrismLauncher/tree/11.1.1\nFriends updater source: https://github.com/chengweialan/mc-friends-client/tree/main/updater\nZulu OpenJDK source: https://www.azul.com/downloads/?package=jdk#zulu\n')
        sums+=hashlib.sha256(output.read_bytes()).hexdigest()+'  '+output.name+'\n'
    mac_patch=destination/'FriendsMC-macOS-Update.zip'
    with zipfile.ZipFile(mac_patch,'w',zipfile.ZIP_DEFLATED) as z:
        z.write(updater,'tools/friends-updater.jar')
        z.write(client/'tools/fool-updater.jar','tools/fool-updater.jar')
        z.write(client/'tools/packwiz-installer.jar','tools/packwiz-installer.jar')
        z.write(client/'tools/packwiz-installer-bootstrap.jar','tools/packwiz-installer-bootstrap.jar')
        entry=zipfile.ZipInfo('Start.command');entry.create_system=3;entry.external_attr=0o100755<<16
        z.writestr(entry,(ROOT/'mac-source/Start.command').read_bytes())
        z.write(ROOT/'download-sources.json','download-sources.json')
        z.write(ROOT/'MOD-CREDITS.md','MOD-CREDITS.md')
        z.write(ROOT/'NETWORK-UPDATE.md','更新说明.md')
        for p in (ROOT/'mirror-licenses').glob('*'):
            if p.is_file(): z.write(p,'licenses/mods/'+p.name)
    sums+=hashlib.sha256(mac_patch.read_bytes()).hexdigest()+'  '+mac_patch.name+'\n'
    write(destination/'SHA256SUMS.txt',sums)
    print(f'Built {archive}: {archive.stat().st_size} bytes, SHA256 {digest}')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--cache',type=Path,default=ROOT/'.build-cache')
    parser.add_argument('--output',type=Path,default=ROOT/'dist')
    args=parser.parse_args()
    build(args.cache.resolve(),args.output.resolve())
