param([switch]$PrepareOnly, [string]$StatusPath='', [ValidateSet('friends','fool')][string]$Pack='friends')
if ($Pack -eq 'fool') {
    & (Join-Path $PSScriptRoot 'Start-Fool.ps1') -PrepareOnly:$PrepareOnly -StatusPath $StatusPath
    exit $LASTEXITCODE
}
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$script:StatusPath = $StatusPath
$script:ReleaseLabel = ''
. (Join-Path $PSScriptRoot 'Progress.ps1')
try {
    Write-ClientProgress 1 '检查本地环境' '正在校验 Java、更新器与启动器文件'
    . (Join-Path $PSScriptRoot 'Common.ps1')
    Assert-Tools
    $launcher = Join-Path $Root 'launcher/Plain Craft Launcher 2.exe'
    if (!(Test-Path -LiteralPath $launcher)) { throw 'PCL executable is missing. Extract the complete bundle first.' }
    $active = Get-Process -Name 'Plain Craft Launcher 2' -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $launcher }
    if ($active) { throw 'Close this bundle''s PCL window and game, then reopen Start.cmd to synchronize safely.' }
    $lock = [IO.File]::Open((Join-Path $Root '.start.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    try {
        $launcherHash = Initialize-PclProtection
        Write-ClientProgress 2 '核对服务器版本' '正在获取最新发布清单，请保持网络连接'
        $channel = Get-Channel
        $script:ReleaseLabel = 'MC '+$channel.minecraft+'  /  NeoForge '+$channel.neoforge+'  /  整合包 '+$channel.release
        $id = 'FriendsMC-' + $channel.minecraft + '-' + $channel.neoforge
        $mcDir = Join-Path $Root 'launcher/.minecraft'
        $instance = Join-Path $mcDir ('versions/'+$id)
        $versionJson = Join-Path $instance ($id+'.json')
        if (Test-Path -LiteralPath $versionJson) {
            $receiptPath = Join-Path $instance 'friends-release.json'
            if (!(Test-Path -LiteralPath $receiptPath)) { throw 'This instance was not installed from our PCL pack. Do not rename an unrelated instance.' }
            $receipt = Get-Content $receiptPath -Raw | ConvertFrom-Json
            if ($receipt.minecraft -ne $channel.minecraft -or $receipt.neoforge -ne $channel.neoforge) { throw 'Installed loader does not match the published release.' }
            Invoke-PackSync $channel $instance
            $channel | ConvertTo-Json | Set-Content $receiptPath -Encoding UTF8
            Set-PclIni (Join-Path $instance 'PCL/Setup.ini') 'VersionArgumentIndieV2' 'True'
            Set-PclIni (Join-Path $instance 'PCL/Setup.ini') 'VersionArgumentJavaV2' '2'
            Set-PclIni (Join-Path $mcDir 'PCL.ini') 'Version' ($instance+'\')
            Write-Host 'Synchronized. Sign in and click Launch in PCL.'
        } else {
            # PCL imports modpack.mrpack next to its EXE on startup.
            if (Test-Path -LiteralPath $instance) { throw 'PCL installation is incomplete. Open PCL to repair it, or rename the incomplete version folder before retrying.' }
            $stage = Join-Path $Root ('state/import-'+$id)
            $overrides = Join-Path $stage 'overrides'
            New-Item -ItemType Directory -Force -Path $overrides | Out-Null
            Invoke-PackSync $channel $overrides
            if (!(Test-Path (Join-Path $overrides 'servers.dat'))) { Copy-Item (Join-Path $Root 'templates/servers.dat') (Join-Path $overrides 'servers.dat') }
            $channel | ConvertTo-Json | Set-Content (Join-Path $overrides 'friends-release.json') -Encoding UTF8
            Set-PclIni (Join-Path $overrides 'PCL/Setup.ini') 'VersionArgumentIndie' '1'
            Set-PclIni (Join-Path $overrides 'PCL/Setup.ini') 'VersionArgumentIndieV2' 'True'
            Set-PclIni (Join-Path $overrides 'PCL/Setup.ini') 'VersionArgumentJavaV2' '2'
            New-PclImport $channel $id $stage
            Write-Host 'PCL will install the prepared pack automatically. Accept its first-run prompts, then sign in and click Launch.'
        }
        New-Item -ItemType Directory -Force -Path $mcDir | Out-Null
        Set-PclIni (Join-Path $Root 'launcher/PCL/Setup.ini') 'LaunchFolderSelect' ($mcDir+'\')
        $env:JAVA_HOME = Split-Path (Split-Path $Java -Parent) -Parent
        $env:PATH = (Split-Path $Java -Parent)+';'+$env:PATH
        Write-ClientProgress 4 '准备打开 PCL' '版本与模组已对齐，即将交给启动器'
        Assert-PclUnchanged $launcherHash
        if (!$PrepareOnly) { Start-Process -FilePath $launcher -WorkingDirectory (Split-Path $launcher) }
        $finishedDetail = if ($PrepareOnly) { '文件检查已完成，本次未打开 PCL。' } else { 'PCL 已打开。登录账号后，点击「启动游戏」。' }
        Write-ClientProgress 4 '准备就绪' $finishedDetail -State 'complete'
    } finally { $lock.Dispose() }
} catch {
    Write-ClientProgress 0 '暂时无法完成更新' $_.Exception.Message -State 'error'
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
