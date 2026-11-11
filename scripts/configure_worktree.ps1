$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$branch = git -C $repo branch --show-current
if ($LASTEXITCODE -ne 0 -or $branch -eq 'master' -or -not $branch) {
    throw 'Configure only an authorized project worktree on a non-master branch.'
}
# Enable per-worktree settings; shared origin URLs and the main checkout stay intact.
git -C $repo config extensions.worktreeConfig true
if ($LASTEXITCODE -ne 0) { throw 'Cannot enable worktree configuration.' }
foreach ($remote in (git -C $repo remote)) {
    git -C $repo config --worktree --replace-all "remote.$remote.pushurl" DISABLED
    if ($LASTEXITCODE -ne 0) { throw "Cannot disable push for $remote." }
}
git -C $repo config --worktree core.hooksPath .githooks
if ($LASTEXITCODE -ne 0) { throw 'Cannot install project push guard.' }
Write-Output "OK project worktree configured: $repo ($branch)"
