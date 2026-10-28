$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../../client-source/scripts/Common.ps1')
$sourceRoot = $script:Root
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('friendsmc-pcl-test-' + [guid]::NewGuid().ToString('N'))
$script:Root = $testRoot
$script:notices = 0
function Require([bool]$Condition, [string]$Message) {
    if (!$Condition) { throw $Message }
}
function Show-PclUpdateNotice {
    $saved = Get-Content -LiteralPath (Join-Path $script:Root 'launcher/PCL/Setup.ini') -Encoding UTF8
    Require ($saved -contains 'SystemSystemUpdate:1') 'Policy must be applied before the notice.'
    $script:notices++
}
try {
    $settings = Join-Path $testRoot 'launcher/PCL/Setup.ini'
    $launcher = Join-Path $testRoot 'launcher/Plain Craft Launcher 2.exe'
    New-Item -ItemType Directory -Path (Split-Path $settings) -Force | Out-Null
    [IO.File]::WriteAllText($launcher, 'launcher sentinel')
    [IO.File]::WriteAllText($settings, "LaunchFolderSelect:C:\Games\Minecraft\`r`nSystemSystemUpdate:0`r`nUiLogoText:original`r`nSystemSystemUpdate:3`r`n")
    $expected = (Get-FileHash -LiteralPath $launcher -Algorithm SHA256).Hash
    $actual = Initialize-PclProtection
    Require ($actual -eq $expected) 'Policy must retain the existing launcher.'
    $saved = @(Get-Content -LiteralPath $settings -Encoding UTF8)
    Require (@($saved | Where-Object { $_.StartsWith('SystemSystemUpdate:') }).Count -eq 1) 'Remove duplicate update settings.'
    Require ($saved -contains 'SystemSystemUpdate:1') 'Keep notifications; prohibit automatic downloads.'
    Require ($saved -contains 'UiLogoText:original') 'Preserve unrelated settings.'
    Require ($saved -contains 'LaunchFolderSelect:C:\Games\Minecraft\') 'Preserve selected game directory.'
    Assert-PclUnchanged $actual
    $null = Initialize-PclProtection
    Require ($script:notices -eq 2) 'Show the compatibility notice on every run.'
    Set-PclIni $settings 'SystemSystemUpdate' '0'
    $null = Initialize-PclProtection
    Require ((Get-Content -LiteralPath $settings) -contains 'SystemSystemUpdate:1') 'Reapply the policy after settings change.'
    [IO.File]::WriteAllText($launcher, 'unexpected replacement')
    $rejected = $false
    try { Assert-PclUnchanged $actual } catch { $rejected = $true }
    Require $rejected 'Reject a launcher replaced during sync.'

    # Check every executable entry path enforces policy before network sync and launch.
    foreach ($name in @('Start.ps1', 'Start-Fool.ps1')) {
        $tokens = $null; $parseErrors = $null
        $ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $sourceRoot ('scripts/' + $name)), [ref]$tokens, [ref]$parseErrors)
        Require ($parseErrors.Count -eq 0) ('Invalid PowerShell syntax: ' + $name)
        $commands = @($ast.FindAll({param($node) $node -is [Management.Automation.Language.CommandAst]}, $true))
        $policy = @($commands | Where-Object { $_.GetCommandName() -eq 'Initialize-PclProtection' })
        $sync = @($commands | Where-Object { $_.GetCommandName() -in @('Get-Channel', 'Invoke-FoolTool') })
        $guard = @($commands | Where-Object { $_.GetCommandName() -eq 'Assert-PclUnchanged' })
        $launch = @($commands | Where-Object { $_.GetCommandName() -eq 'Start-Process' })
        Require ($policy.Count -eq 1 -and $guard.Count -eq 1 -and $launch.Count -eq 1 -and $sync.Count -gt 0) ('Missing protection: ' + $name)
        Require ($policy[0].Extent.StartOffset -lt $sync[0].Extent.StartOffset) ('Network access precedes policy: ' + $name)
        Require ($guard[0].Extent.StartOffset -lt $launch[0].Extent.StartOffset) ('Launch precedes hash guard: ' + $name)
    }
    Write-Output 'PASS: PCL notify-only policy, setting preservation, repeat enforcement, per-run notice, binary guard, both startup paths.'
} finally {
    $script:Root = $sourceRoot
    $resolved = [IO.Path]::GetFullPath($testRoot)
    $tempPrefix = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if (!$resolved.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase) -or (Split-Path $resolved -Leaf) -notlike 'friendsmc-pcl-test-*') {
        throw 'Refusing to remove an unexpected test path.'
    }
    if (Test-Path -LiteralPath $resolved) { Remove-Item -LiteralPath $resolved -Recurse -Force }
}
