#Requires -Version 5.1
[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [string]$KeyPath = (Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) 'privatekey_mbaer.ppk')
)

$ErrorActionPreference = 'Stop'
function Invoke-Native([scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Befehl fehlgeschlagen (Exitcode ${LASTEXITCODE}): $Command"
    }
}
$server = 'eligius.donau-uni.ac.at'
$repository = 'dwb-gitlab.donau-uni.ac.at/zms/eligius'
$hostKey = 'SHA256:9ZnAU1bnPOPbEn5TKxvyDX6k8bmH2mdr4hejQPymWjs'
$remoteScript = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'deploy-production-server.sh')
$buildDirectory = $null

function Invoke-Production([string]$Mode, [string]$Revision = '', [string]$Digest = '', [string]$PreviousImage = '') {
    if ($Mode -notin @('status', 'deploy', 'verify') -or
        $Revision -notmatch '^(|[0-9a-f]{40})$' -or
        $Digest -notmatch '^(|sha256:[0-9a-f]{64})$' -or
        $PreviousImage -notmatch '^(|sha256:[0-9a-f]{64})$') {
        throw 'Invalid production command arguments.'
    }
    $remoteCommand = 'tr -d ''\r'' | bash -s -- ' + "$Mode $Revision $Digest $PreviousImage"
    Invoke-Native { $remoteScript | plink -batch -hostkey $hostKey -i $KeyPath "mbaer@$server" $remoteCommand }
}

function Get-RegistryDigest([string]$Reference) {
    $manifest = Invoke-Native { docker buildx imagetools inspect $Reference --format '{{json .Manifest}}' } | ConvertFrom-Json
    if ($manifest.digest -notmatch '^sha256:[0-9a-f]{64}$') {
        throw "No valid registry digest for $Reference."
    }
    return $manifest.digest
}

function Start-LocalDocker {
    $ErrorActionPreference = 'Continue'
    $version = docker version --format '{{.Server.Version}}' 2>$null
    if ($LASTEXITCODE -ne 0) {
        $desktop = Join-Path $env:ProgramFiles 'Docker/Docker/Docker Desktop.exe'
        if (!(Test-Path -LiteralPath $desktop -PathType Leaf)) {
            throw 'Docker Engine ist nicht erreichbar. Starte Docker Desktop und führe das Skript erneut aus.'
        }
        Write-Host 'Docker Desktop wird gestartet.'
        Start-Process -FilePath $desktop -WindowStyle Hidden
        for ($attempt = 0; $attempt -lt 60; $attempt++) {
            Start-Sleep -Seconds 2
            $version = docker version --format '{{.Server.Version}}' 2>$null
            if ($LASTEXITCODE -eq 0) { break }
        }
        if ($LASTEXITCODE -ne 0) { throw 'Docker Engine wurde nach zwei Minuten nicht bereit.' }
    }
    $type = docker info --format '{{.OSType}}'
    if ($LASTEXITCODE -ne 0 -or $type -ne 'linux') { throw 'Docker Desktop muss Linux-Container verwenden.' }
    Write-Host "Lokale Docker Engine: $version"
}

Push-Location (Join-Path $PSScriptRoot '..')
try {
    Get-Command git, docker, tar, plink | Out-Null
    if (!(Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
        throw "PuTTY key not found: $KeyPath. Set -KeyPath to its location."
    }

    Invoke-Native { git fetch gitlab main }
    $revision = (Invoke-Native { git rev-parse FETCH_HEAD }).Trim()
    if ($revision -notmatch '^[0-9a-f]{40}$') { throw 'Could not resolve GitLab main.' }
    $state = @(Invoke-Production status)
    if ($state.Count -ne 3 -or $state[0] -notmatch '^sha256:[0-9a-f]{64}$' -or
        $state[1] -notmatch '^[0-9a-f]{40}$' -or $state[2] -notmatch '^sha256:[0-9a-f]{64}$') {
        throw 'Production did not return a recognized release state.'
    }
    $previousImage, $previousRevision, $previousDigest = $state
    Invoke-Native { git merge-base --is-ancestor $previousRevision $revision }
    $registryDigest = Get-RegistryDigest "${repository}:latest"
    if ($registryDigest -ne $previousDigest) {
        throw "Registry latest ($registryDigest) and production ($previousDigest) differ. Check whether another release is in progress."
    }
    if (!$CheckOnly -and $previousRevision -eq $revision) {
        Invoke-Production verify $revision $registryDigest
        Write-Host "Bereits live: $revision auf https://$server/"
        return
    }

    Start-LocalDocker
    $tag = "$(Get-Date -Format yyyyMMdd-HHmmss)-$($revision.Substring(0, 7))"
    $candidate = "${repository}:$tag"
    $buildDirectory = Join-Path ([IO.Path]::GetTempPath()) ('eligius-deploy-' + [guid]::NewGuid())
    $source = Join-Path $buildDirectory 'source'
    New-Item -ItemType Directory -Path $source -Force | Out-Null
    $archive = Join-Path $buildDirectory 'source.tar'
    Invoke-Native { git -c core.autocrlf=false archive --format=tar "--output=$archive" $revision }
    Invoke-Native { tar -xf $archive -C $source }
    if ([IO.File]::ReadAllBytes((Join-Path $source 'docker/entrypoint.sh')) -contains 13) {
        throw 'Docker entrypoint contains Windows line endings.'
    }

    Invoke-Native { docker build --platform linux/amd64 --provenance=false --sbom=false --label "org.opencontainers.image.revision=$revision" -t $candidate $source }
    $tests = @('slg.test_oai', 'slg.test_ui_translations', 'slg.test_bildtyp_translations',
        'slg.test_vocabulary_translations', 'slg.test_coin_labels')
    Invoke-Native { docker run --rm --network none --entrypoint /venv/bin/python $candidate manage.py test @tests --settings=djangoproject.test_settings --noinput }
    if ($CheckOnly) {
        Write-Host "Prüflauf erfolgreich: $revision. Das Testimage wurde lokal gebaut."
        return
    }

    Invoke-Native { docker push $candidate }
    $digest = Get-RegistryDigest $candidate
    if ((Get-RegistryDigest "${repository}:latest") -ne $registryDigest) {
        throw 'Registry latest changed during the build. Run the deployment again after checking production.'
    }
    $remoteHead = (Invoke-Native { git ls-remote --exit-code gitlab refs/heads/main }) -split '\s+'
    if ($remoteHead[0] -ne $revision) { throw 'GitLab main changed during the build. Run the deployment again.' }
    Invoke-Production deploy $revision $digest $previousImage

    # Publish latest only after production has started successfully.
    try {
        if ((Get-RegistryDigest "${repository}:latest") -ne $registryDigest) {
            throw 'Registry latest was changed by another process.'
        }
        Invoke-Native { docker tag $candidate "${repository}:latest" }
        Invoke-Native { docker push "${repository}:latest" }
        if ((Get-RegistryDigest "${repository}:latest") -ne $digest) {
            throw 'Registry latest does not match the published release.'
        }
    }
    catch {
        throw "Production started $revision from $candidate ($digest), but registry latest could not be verified. $($_.Exception.Message)"
    }
    Invoke-Production verify $revision $digest
    Write-Host "Live: $revision ($tag) auf https://$server/"
}
finally {
    Pop-Location
    if ($buildDirectory -and (Test-Path -LiteralPath $buildDirectory)) {
        $resolved = (Resolve-Path -LiteralPath $buildDirectory).ProviderPath
        $expected = [IO.Path]::GetFullPath($buildDirectory)
        if ($resolved -eq $expected) {
            Remove-Item -LiteralPath $resolved -Recurse -Force
        }
    }
}
