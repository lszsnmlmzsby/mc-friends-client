param([switch]$PrepareOnly,[string]$StatusPath='')
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
$script:StatusPath=$StatusPath
$script:ReleaseLabel='愚者 · 独立实例'
. (Join-Path $PSScriptRoot 'Progress.ps1')
. (Join-Path $PSScriptRoot 'Common.ps1')
function Invoke-FoolTool([string[]]$Arguments) {
    $info=New-Object Diagnostics.ProcessStartInfo
    $info.FileName=$Java
    $info.UseShellExecute=$false;$info.CreateNoWindow=$true
    $info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    $info.StandardOutputEncoding=[Text.Encoding]::UTF8;$info.StandardErrorEncoding=[Text.Encoding]::UTF8
    $cp=(Join-Path $Root 'tools/friends-updater.jar')+';'+(Join-Path $Root 'tools/fool-updater.jar')
    $info.Arguments='-Dstdout.encoding=UTF-8 -Dstderr.encoding=UTF-8 -cp "'+$cp+'" FoolUpdater '+(($Arguments | ForEach-Object {'"'+$_+'"'}) -join ' ')
    $p=New-Object Diagnostics.Process;$p.StartInfo=$info
    $null=$p.Start();$errors=$p.StandardError.ReadToEndAsync()
    try {
        while (($line=$p.StandardOutput.ReadLine()) -ne $null) {Write-Host $line;Write-ClientProgress 3 '愚者 · 同步整合包' $line}
        $p.WaitForExit();$err=$errors.Result
        if ($p.ExitCode -ne 0) {throw ('愚者同步未完成，游戏未启动。'+$err)}
    } finally {$p.Dispose()}
}
try {
    Assert-Tools
    $launcher=Join-Path $Root 'launcher/Plain Craft Launcher 2.exe'
    if (!(Test-Path -LiteralPath $launcher)) {throw '请将补丁解压覆盖到原 FriendsMC 客户端目录。'}
    $active=Get-Process -Name 'Plain Craft Launcher 2' -ErrorAction SilentlyContinue | Where-Object {$_.Path -eq $launcher}
    if ($active) {throw '请先关闭此客户端的 PCL 和游戏，再运行 Start。'}
    $lock=[IO.File]::Open((Join-Path $Root '.start.lock'),'OpenOrCreate','ReadWrite','None')
    try {
        $launcherHash = Initialize-PclProtection
        New-Item -ItemType Directory -Force -Path (Join-Path $Root 'state') | Out-Null
        $channelFile=Join-Path $Root 'state/fool-channel.json'
        Write-ClientProgress 2 '愚者 · 核对版本' '读取国内更新清单'
        Invoke-FoolTool @('channel',$Root,$channelFile)
        $channel=Get-Content -Raw -Encoding UTF8 -LiteralPath $channelFile | ConvertFrom-Json
        $id='FriendsMC-fool-'+$channel.minecraft+'-'+$channel.forge
        $script:ReleaseLabel='愚者 '+$channel.release+' / MC '+$channel.minecraft+' / Forge '+$channel.forge
        $mcDir=Join-Path $Root 'launcher/.minecraft';$instance=Join-Path $mcDir ('versions/'+$id)
        $exists=Test-Path -LiteralPath (Join-Path $instance ($id+'.json'))
        if ($exists) {
            $receipt=Join-Path $instance 'friends-fool-release.json'
            if (!(Test-Path -LiteralPath $receipt)) {throw '此实例不是由好友服更新器创建，请勿将其他实例改为同名。'}
            $old=Get-Content -Raw -Encoding UTF8 -LiteralPath $receipt | ConvertFrom-Json
            if ($old.minecraft -ne $channel.minecraft -or $old.forge -ne $channel.forge) {throw '实例游戏版本或 Forge 与发布清单不一致。'}
            $game=$instance
        } else {
            if (Test-Path -LiteralPath $instance) {throw '上次 PCL 安装尚未完成，请先在 PCL 中完成或修复愚者安装。'}
            $stage=Join-Path $Root ('state/import-'+$id);$game=Join-Path $stage 'overrides'
        }
        New-Item -ItemType Directory -Force -Path $game | Out-Null
        Invoke-FoolTool @('sync',$Root,$game,$channelFile)
        $channel | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $game 'friends-fool-release.json') -Encoding UTF8
        Set-PclIni (Join-Path $game 'PCL/Setup.ini') 'VersionArgumentIndieV2' 'True'
        Set-PclIni (Join-Path $game 'PCL/Setup.ini') 'VersionArgumentJavaV2' '2'
        if (!$exists) {
            Set-PclIni (Join-Path $game 'PCL/Setup.ini') 'VersionRamType' '1'
            Set-PclIni (Join-Path $game 'PCL/Setup.ini') 'VersionRamCustom' '21'
        }
        if (!(Test-Path -LiteralPath (Join-Path $game 'servers.dat'))) {Copy-Item -LiteralPath (Join-Path $Root 'templates/servers.dat') -Destination (Join-Path $game 'servers.dat')}
        if (!$exists) {
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            $manifest=@{formatVersion=1;game='minecraft';versionId=$channel.release;name=$id;summary='Friends MC - The Fool';files=@();dependencies=@{minecraft=$channel.minecraft;forge=$channel.forge}}
            [IO.File]::WriteAllText((Join-Path $stage 'modrinth.index.json'),($manifest|ConvertTo-Json -Depth 5),(New-Object Text.UTF8Encoding($false)))
            $temp=Join-Path $Root ('state/fool-import-'+[guid]::NewGuid().ToString('N')+'.mrpack')
            Write-ClientProgress 3 '准备 PCL 首次导入' '只在首次安装打包；之后 Start 直接增量更新'
            [IO.Compression.ZipFile]::CreateFromDirectory($stage,$temp,[IO.Compression.CompressionLevel]::NoCompression,$false)
            $pending=Join-Path $Root 'launcher/modpack.mrpack'
            if (Test-Path -LiteralPath $pending) {Move-Item -LiteralPath $pending -Destination (Join-Path $Root ('state/previous-import-'+[guid]::NewGuid().ToString('N')+'.mrpack'))}
            Move-Item -LiteralPath $temp -Destination $pending
        } else {Set-PclIni (Join-Path $mcDir 'PCL.ini') 'Version' ($instance+'\')}
        Set-PclIni (Join-Path $Root 'launcher/PCL/Setup.ini') 'LaunchFolderSelect' ($mcDir+'\')
        Assert-PclUnchanged $launcherHash
        if (!$PrepareOnly) {Start-Process -FilePath $launcher -WorkingDirectory (Split-Path $launcher)}
        $detail=if ($PrepareOnly) {'愚者同步完成，本次未打开 PCL。'} elseif (!$exists) {'请确认 PCL 首次导入，登录正版账号并选择愚者；进服前确认服主已切换服务器。'} else {'选择愚者实例启动；进服前确认服主已切换服务器。'}
        Write-ClientProgress 4 '愚者准备就绪' $detail -State 'complete'
    } finally {$lock.Dispose()}
} catch {Write-ClientProgress 0 '愚者更新未完成' $_.Exception.Message -State 'error';Write-Host $_.Exception.Message;exit 1}
exit 0
