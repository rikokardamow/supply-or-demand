# Registers this project's scheduled pulls as Windows Task Scheduler tasks --
# see infra/README.md for the lake-on-laptop decision this implements (GitHub
# Actions stays CI-only; the actual data pulls run here, on the machine that
# holds the real .env secrets and the data/ lake).
#
# Idempotent: /F overwrites an existing task of the same name, so re-running
# this script after editing it (or after moving the repo) is always safe.
#
# Trigger times below are UTC targets translated to this project's own release
# calendar (see root NOTES.md) -- Task Scheduler triggers on LOCAL time, so
# these are a reasonable evening/afternoon approximation, not minute-perfect UTC.
# Known, accepted limitation: local-time triggers drift by ~1h across DST
# transitions -- fine for a solo analyst's own daily/weekly pulls, not engineered
# away here.
#
# Run this script from an elevated PowerShell prompt (Task Scheduler task
# creation for the current user does not require elevation, but registering
# under "highest privileges" does -- plain /Create as the current user is enough
# for this project's own use case, no elevation required).

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

function Register-Task {
    param(
        [string]$Name,
        [string]$Cadence,
        [string]$Schedule,   # schtasks /SC value: DAILY, WEEKLY, MONTHLY
        [string]$Day,        # /D value: MON..SUN for WEEKLY, 1-31 for MONTHLY (omit for DAILY)
        [string]$StartTime   # /ST value, HH:mm, local time
    )

    $TaskRun = "`"$Python`" -m infra.run_scheduled --cadence $Cadence"
    $Args = @(
        "/Create", "/F",
        "/SC", $Schedule,
        "/TN", "EnergyDashboard\$Name",
        "/TR", $TaskRun,
        "/ST", $StartTime
    )
    if ($Day) {
        $Args += @("/D", $Day)
    }

    Write-Host "Registering $Name ($Schedule$(if ($Day) { " /D $Day" }) at $StartTime local)..."
    & schtasks.exe @Args
}

# Daily evening pull -- GIE, ENTSOG, ENTSO-E, EirGrid, gridstatus (CAISO/NYISO),
# weather, news (GDELT/Guardian), OFAC sanctions. Target ~19:45 UTC.
Register-Task -Name "PullDaily" -Cadence "daily" -Schedule "DAILY" -StartTime "20:45"

# EIA WPSR -- published Wed after 10:30 ET; target ~15:45 UTC.
Register-Task -Name "PullWpsr" -Cadence "wpsr" -Schedule "WEEKLY" -Day "WED" -StartTime "16:45"

# EIA weekly natural gas storage -- published Thu after 10:30 ET; target ~15:45 UTC.
Register-Task -Name "PullNgStorage" -Cadence "ng_storage" -Schedule "WEEKLY" -Day "THU" -StartTime "16:45"

# Baker Hughes rig count + macro (FRED/Frankfurter/Eurostat) + Adanos sentiment --
# Friday, target ~19:00 UTC.
Register-Task -Name "PullWeeklyFri" -Cadence "weekly_fri" -Schedule "WEEKLY" -Day "FRI" -StartTime "20:00"

# OPEC MOMR + JODI + EIA monthly PADD flows/production-exports -- twice monthly,
# the 13th and 21st (MOMR ~11th-14th, JODI ~20th), target ~09:00 UTC. Two
# separate tasks since schtasks' own MONTHLY /D takes one day value at a time.
Register-Task -Name "PullMonthly13th" -Cadence "monthly" -Schedule "MONTHLY" -Day "13" -StartTime "10:00"
Register-Task -Name "PullMonthly21st" -Cadence "monthly" -Schedule "MONTHLY" -Day "21" -StartTime "10:00"

Write-Host ""
Write-Host "Done. Verify with: schtasks /Query /TN EnergyDashboard\PullDaily /V /FO LIST"
Write-Host "Remove one with:   schtasks /Delete /TN EnergyDashboard\PullDaily /F"
