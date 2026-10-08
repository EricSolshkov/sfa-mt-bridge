param([switch]$Tests)
$ErrorActionPreference = 'Stop'
$project = $PSScriptRoot
$toolsRoot = Join-Path (Split-Path $project) 'analysis/android-build'
if (-not $env:JAVA_HOME) {
    $jdk = Get-ChildItem (Join-Path $toolsRoot 'jdk') -Directory -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $jdk) { throw 'Set JAVA_HOME to JDK 17 first.' }
    $env:JAVA_HOME = $jdk.FullName
}
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"
if (-not (Test-Path (Join-Path $project 'local.properties'))) {
    $sdk = if ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { Join-Path $toolsRoot 'sdk' }
    Set-Content (Join-Path $project 'local.properties') ('sdk.dir=' + $sdk.Replace('\','/')) -Encoding utf8
}
$gradle = Join-Path $project 'gradlew.bat'
$tasks = @('assemblePhoneDebug', 'assembleEmulatorDebug')
if ($Tests) { $tasks += @('testPhoneDebugUnitTest', 'lintPhoneDebug') }
& $gradle -p $project --console=plain @tasks
if ($LASTEXITCODE -ne 0) { throw "Gradle failed: $LASTEXITCODE" }
