"""Convert the author's extracted mrpack to a native packwiz client release.

Run locally. Keep source archives, downloaded binaries and upload tickets out of Git.
The generated release preserves personal options; gameplay configs stay managed.
"""
import argparse, concurrent.futures, hashlib, json, shutil, time, urllib.request
from pathlib import Path, PurePosixPath
from fool_customizations import CONFIG, apply_customizations

BASE_URL = 'https://friends-mc-downloads-1318356926.cos.ap-beijing.myqcloud.com/friends-mc/packs/fool'

def digest(path, algorithm='sha256'):
    h = hashlib.new(algorithm)
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()

def safe(root, relative):
    p = PurePosixPath(relative)
    if p.is_absolute() or any(x in ('..', '.') for x in p.parts) or ':' in relative or '\\' in relative:
        raise ValueError('Invalid path: '+relative)
    target = root.joinpath(*p.parts)
    if not target.resolve().is_relative_to(root.resolve()): raise ValueError(relative)
    return target

def personal(path):
    return path in ('options.txt','TrashSlotSaveState.json','CustomSkinLoader/CustomSkinLoader.json') or path.startswith((
        'config/jei/','config/inventoryprofilesnext/','config/jade/','config/xaerominimap',
        'config/xaeroworldmap','config/xaeropatreon','config/embeddium-options',
        'config/oculus.properties','config/MouseTweaks','config/appleskin-client'))

def build(source, server, output, release, base_url=BASE_URL):
    manifest = json.loads((source/'modrinth.index.json').read_text(encoding='utf-8-sig'))
    if manifest['dependencies'] != {'minecraft':'1.20.1','forge':'47.4.12'}:
        raise ValueError('Review game/loader version before importing a new upstream release')
    game=output/'game'; stage=output/'mirror'; pub=stage/'releases'/release
    for d in (game, pub, stage/'objects'): d.mkdir(parents=True, exist_ok=True)
    # Only pack-owned paths. Never import author launcher state/accounts or worlds.
    allowed={'config','defaultconfigs','kubejs','mods','resourcepacks','shaderpacks','CustomSkinLoader','options.txt','TrashSlotSaveState.json'}
    for f in (source/'overrides').rglob('*'):
        if not f.is_file(): continue
        rel=f.relative_to(source/'overrides').as_posix()
        if rel.split('/')[0] not in allowed or f.name=='embeddium-fingerprint.json': continue
        dst=safe(game,rel);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dst)
    def obtain(item):
        rel=item['path']; dst=safe(game,rel)
        algorithm='sha512' if 'sha512' in item['hashes'] else 'sha1'; expected=item['hashes'][algorithm]
        if dst.exists() and dst.stat().st_size==item['fileSize'] and digest(dst,algorithm)==expected: return
        for candidate in (safe(server,rel), safe(server,rel+'.disabled')):
            if candidate.is_file() and candidate.stat().st_size==item['fileSize'] and digest(candidate,algorithm)==expected:
                dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(candidate,dst); return
        errors=[]
        for url in sorted(item['downloads'],key=lambda u:0 if 'cdn.modrinth.com' in u else 1):
            for attempt in range(2):
                try:
                    req=urllib.request.Request(url,headers={'User-Agent':'FriendsMC/Fool-import'})
                    dst.parent.mkdir(parents=True,exist_ok=True); tmp=dst.with_name(dst.name+'.download')
                    with urllib.request.urlopen(req,timeout=45) as src, tmp.open('wb') as f: shutil.copyfileobj(src,f)
                    if tmp.stat().st_size!=item['fileSize'] or digest(tmp,algorithm)!=expected: raise ValueError('Incomplete upstream file')
                    tmp.replace(dst);return
                except Exception as e: errors.append(type(e).__name__);time.sleep(attempt)
        raise RuntimeError('Unable to download '+rel+': '+','.join(errors))
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures={pool.submit(obtain,item):item['path'] for item in manifest['files']}
        for n,future in enumerate(concurrent.futures.as_completed(futures),1):
            future.result()
            if n%20==0 or n==len(futures): print(f'Prepared {n}/{len(futures)} upstream files',flush=True)
    index=['hash-format = "sha256"\n']; stats={'mods':0,'files':0,'bytes':0}; records=[]
    # Import only the approved upstream inventory; do not include stale files from an earlier import.
    inventory={x['path'] for x in manifest['files']}
    inventory.update(f.relative_to(source/'overrides').as_posix() for f in (source/'overrides').rglob('*') if f.is_file()
        and f.relative_to(source/'overrides').parts[0] in allowed and f.name!='embeddium-fingerprint.json')
    if CONFIG.as_posix() not in inventory:
        raise ValueError('Upstream pack is missing '+CONFIG.as_posix()+'; review book retention compatibility')
    inventory.update(apply_customizations(game))
    quote=lambda x:json.dumps(x,ensure_ascii=False)
    for rel in sorted(inventory):
        f=safe(game,rel); sha=digest(f); size=f.stat().st_size
        stats['files']+=1;stats['bytes']+=size
        if rel.startswith(('mods/','resourcepacks/','shaderpacks/')) or size>1024*1024:
            obj=stage/'objects'/sha
            if not obj.exists(): shutil.copy2(f,obj)
            name=PurePosixPath(rel).name
            metadata=rel+'.pw.toml'
            text=f'name = {quote(name)}\nfilename = {quote(name)}\nside = "client"\n\n[download]\nurl = {quote(base_url+"/objects/"+sha)}\nhash-format = "sha256"\nhash = "{sha}"\n'
            if rel.startswith('shaderpacks/') and rel.endswith('.zip'):
                text+='\n[option]\noptional = true\ndefault = false\ndescription = "可选光影包，不影响进服；游戏内自行选择启用。"\n'
            target=safe(pub,metadata);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text,encoding='utf-8')
            index.append(f'\n[[files]]\nfile = {quote(metadata)}\nhash = "{digest(target)}"\nmetafile = true\n')
            if rel.startswith('mods/') and rel.endswith('.jar'): stats['mods']+=1
        else:
            target=safe(pub,rel);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,target)
            index.append(f'\n[[files]]\nfile = {quote(rel)}\nhash = "{sha}"\n'+('preserve = true\n' if personal(rel) else ''))
        records.append({'path':rel,'sha256':sha,'size':size,'preserve':personal(rel)})
    (pub/'index.toml').write_text(''.join(index),encoding='utf-8')
    (pub/'pack.toml').write_text(f'name = "Friends MC · 愚者"\nauthor = "流霜雾影；好友服维护"\nversion = "{release}"\npack-format = "packwiz:1.1.0"\n\n[index]\nfile = "index.toml"\nhash-format = "sha256"\nhash = "{digest(pub/"index.toml")}"\n\n[versions]\nminecraft = "1.20.1"\nforge = "47.4.12"\n',encoding='utf-8')
    (output/'inventory.json').write_text(json.dumps({'release':release,'upstream':'0.3.0','minecraft':'1.20.1','forge':'47.4.12','java':17,'stats':stats,'files':records},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(stats),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--server',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--release',required=True)
    a=p.parse_args();build(a.source,a.server,a.output,a.release)
