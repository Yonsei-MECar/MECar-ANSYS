[CmdletBinding()]
param(
    [ValidateSet('Plan', 'Install', 'Uninstall', 'Status', 'Health')]
    [string]$Action = 'Plan',
    [string]$TaskName = 'MECar-Analysis-Agent',
    [string]$RuntimeRoot,
    [string]$ConfigPath,
    [string]$PythonExe,
    [string]$ProfilesRoot,
    [string]$ServiceAccount,
    [switch]$Apply,
    [switch]$EnableTask,
    [switch]$PromptForCredential
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-SafeTaskName([string]$Value) {
    if ($Value -notmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$') {
        throw 'TaskName must be a safe ASCII identifier.'
    }
}

function Resolve-RequiredAbsolutePath([string]$Value, [string]$Field, [ValidateSet('File', 'Directory', 'FutureDirectory')] [string]$Kind) {
    if ([string]::IsNullOrWhiteSpace($Value) -or -not [IO.Path]::IsPathRooted($Value) -or $Value.Contains('"')) {
        throw "$Field must be an absolute path without quote characters."
    }
    $Full = [IO.Path]::GetFullPath($Value)
    if ($Kind -eq 'File' -and -not [IO.File]::Exists($Full)) {
        throw "$Field file does not exist."
    }
    if ($Kind -eq 'Directory' -and -not [IO.Directory]::Exists($Full)) {
        throw "$Field directory does not exist."
    }
    if ($Kind -eq 'FutureDirectory') {
        $Root = [IO.Path]::GetPathRoot($Full)
        if ($Full.TrimEnd('\') -eq $Root.TrimEnd('\')) {
            throw "$Field must not be a filesystem root."
        }
    }
    return $Full.TrimEnd('\')
}

function Quote-TaskArgument([string]$Value) {
    if ($Value.Contains('"') -or $Value.EndsWith('\')) {
        throw 'Unsafe scheduled-task argument.'
    }
    return '"' + $Value + '"'
}

function Get-AgentCommandPlan {
    $ResolvedRuntime = Resolve-RequiredAbsolutePath $RuntimeRoot 'RuntimeRoot' 'FutureDirectory'
    $ResolvedConfig = Resolve-RequiredAbsolutePath $ConfigPath 'ConfigPath' 'File'
    $ResolvedPython = Resolve-RequiredAbsolutePath $PythonExe 'PythonExe' 'File'
    $ResolvedProfiles = $null
    if (-not [string]::IsNullOrWhiteSpace($ProfilesRoot)) {
        $ResolvedProfiles = Resolve-RequiredAbsolutePath $ProfilesRoot 'ProfilesRoot' 'Directory'
    }
    $Config = Get-Content -LiteralPath $ResolvedConfig -Raw -Encoding UTF8 | ConvertFrom-Json
    $AgentProperty = $Config.PSObject.Properties['agent']
    $AgentEnabled = $null -ne $AgentProperty -and $null -ne $AgentProperty.Value.PSObject.Properties['enabled'] -and $AgentProperty.Value.enabled -eq $true
    $ExternalProperty = $Config.PSObject.Properties['external_execution_enabled']
    $ExternalExecutionEnabled = $null -ne $ExternalProperty -and $ExternalProperty.Value -eq $true
    $ArgumentParts = @('-m', 'mecar_automation', '--runtime-root', (Quote-TaskArgument $ResolvedRuntime))
    if ($null -ne $ResolvedProfiles) {
        $ArgumentParts += @('--profiles', (Quote-TaskArgument $ResolvedProfiles))
    }
    $ArgumentParts += @('--config', (Quote-TaskArgument $ResolvedConfig), 'agent')
    return [pscustomobject]@{
        RuntimeRoot = $ResolvedRuntime
        ConfigPath = $ResolvedConfig
        PythonExe = $ResolvedPython
        ProfilesRoot = $ResolvedProfiles
        AgentEnabled = $AgentEnabled
        ExternalExecutionEnabled = $ExternalExecutionEnabled
        Arguments = ($ArgumentParts -join ' ')
    }
}

Assert-SafeTaskName $TaskName

if ($Action -eq 'Plan') {
    $Missing = @()
    foreach ($Pair in @(@('RuntimeRoot', $RuntimeRoot), @('ConfigPath', $ConfigPath), @('PythonExe', $PythonExe))) {
        if ([string]::IsNullOrWhiteSpace([string]$Pair[1])) { $Missing += $Pair[0] }
    }
    if ($Missing.Count -gt 0) {
        [pscustomobject]@{
            Action = 'Plan'
            Apply = $false
            DefaultTaskState = 'Disabled'
            MissingRequiredValues = $Missing
            CredentialOnCommandLine = $false
        } | ConvertTo-Json -Depth 6
        exit 0
    }
    $Plan = Get-AgentCommandPlan
    [pscustomobject]@{
        Action = 'Plan'
        Apply = $false
        DefaultTaskState = 'Disabled'
        AgentEnabled = $Plan.AgentEnabled
        ExternalExecutionEnabled = $Plan.ExternalExecutionEnabled
        Execute = $Plan.PythonExe
        Arguments = $Plan.Arguments
        CredentialOnCommandLine = $false
    } | ConvertTo-Json -Depth 6
    exit 0
}

if ($Action -eq 'Status') {
    $Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $Task) {
        [pscustomobject]@{ TaskName = $TaskName; Installed = $false; State = 'ABSENT' } | ConvertTo-Json
        exit 0
    }
    $Info = Get-ScheduledTaskInfo -TaskName $TaskName
    [pscustomobject]@{
        TaskName = $TaskName
        Installed = $true
        State = [string]$Task.State
        LastRunTime = $Info.LastRunTime
        LastTaskResult = $Info.LastTaskResult
        NextRunTime = $Info.NextRunTime
    } | ConvertTo-Json -Depth 4
    exit 0
}

if ($Action -eq 'Uninstall') {
    if (-not $Apply) {
        [pscustomobject]@{ Action = 'Uninstall'; Apply = $false; TaskName = $TaskName } | ConvertTo-Json
        exit 0
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
    [pscustomobject]@{ Action = 'Uninstall'; Applied = $true; TaskName = $TaskName } | ConvertTo-Json
    exit 0
}

$CommandPlan = Get-AgentCommandPlan

if ($Action -eq 'Health') {
    $Arguments = @('-m', 'mecar_automation', '--runtime-root', $CommandPlan.RuntimeRoot)
    if ($null -ne $CommandPlan.ProfilesRoot) { $Arguments += @('--profiles', $CommandPlan.ProfilesRoot) }
    $Arguments += @('--config', $CommandPlan.ConfigPath, 'health')
    & $CommandPlan.PythonExe @Arguments
    exit $LASTEXITCODE
}

if ([string]::IsNullOrWhiteSpace($ServiceAccount) -or $ServiceAccount -notmatch '^[A-Za-z0-9_.@\\-]{1,128}$') {
    throw 'Install requires an explicit safe ServiceAccount.'
}
if (-not $CommandPlan.AgentEnabled) {
    throw 'Install requires agent.enabled=true in the approved config.'
}
if (-not $Apply) {
    [pscustomobject]@{
        Action = 'Install'
        Apply = $false
        TaskName = $TaskName
        ServiceAccount = $ServiceAccount
        DefaultTaskState = 'Disabled'
        EnableTaskRequested = [bool]$EnableTask
        Execute = $CommandPlan.PythonExe
        Arguments = $CommandPlan.Arguments
        CredentialOnCommandLine = $false
    } | ConvertTo-Json -Depth 6
    exit 0
}
if (-not $PromptForCredential) {
    throw 'Install -Apply requires -PromptForCredential; credential command-line parameters are forbidden.'
}

$AccountCredential = Get-Credential -UserName $ServiceAccount -Message 'Task Scheduler service account credential'
if ($AccountCredential.UserName -ne $ServiceAccount) {
    throw 'Credential account does not match ServiceAccount.'
}
$TaskAction = New-ScheduledTaskAction -Execute $CommandPlan.PythonExe -Argument $CommandPlan.Arguments -WorkingDirectory $CommandPlan.RuntimeRoot
$TaskTrigger = New-ScheduledTaskTrigger -AtStartup
$TaskSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
$SecretText = $AccountCredential.GetNetworkCredential().Password
try {
    Register-ScheduledTask -TaskName $TaskName -Action $TaskAction -Trigger $TaskTrigger -Settings $TaskSettings -User $AccountCredential.UserName -Password $SecretText -RunLevel Highest -Force | Out-Null
} finally {
    $SecretText = $null
    $AccountCredential = $null
}
if ($EnableTask) {
    Enable-ScheduledTask -TaskName $TaskName | Out-Null
    $FinalState = 'Enabled'
} else {
    Disable-ScheduledTask -TaskName $TaskName | Out-Null
    $FinalState = 'Disabled'
}
[pscustomobject]@{ Action = 'Install'; Applied = $true; TaskName = $TaskName; State = $FinalState } | ConvertTo-Json
