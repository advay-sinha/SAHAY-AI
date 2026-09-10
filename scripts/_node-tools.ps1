# Dot-sourced helper: resolve npm and npx from the Node install that is
# actually on PATH, instead of trusting whichever `npm` PATH finds first.
#
# Why: this machine's PATH carries a stale entry,
#     C:\Program Files\nodejs\node_modules\npm\bin
# ahead of C:\Program Files\nodejs. The npm.ps1 in that directory computes a
# doubled prefix and dies with:
#     Cannot find module '...\npm\bin\node_modules\npm\bin\npm-prefix.js'
# Whether it wins depends on PATH order in the shell that launched the script,
# so the same command passes in one terminal and fails in another. Resolving
# the shims next to node.exe makes every script independent of that.

$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) { throw "node is not on PATH. Install Node.js 24 LTS (EXT-113)." }

$nodeDir = Split-Path -Parent $node.Source
$script:Npm = Join-Path $nodeDir "npm.cmd"
$script:Npx = Join-Path $nodeDir "npx.cmd"

foreach ($tool in @($script:Npm, $script:Npx)) {
    if (-not (Test-Path $tool)) { throw "Expected $tool next to node.exe; the Node install looks incomplete." }
}
