# Windows PowerShell version of run_agent.sh.
# Run from the repository root:  powershell -ExecutionPolicy Bypass -File evals\run_agent.ps1
$ErrorActionPreference = "Continue"
Get-ChildItem evals\cases -File | Where-Object { $_.Extension -ne ".json" } | ForEach-Object {
    $stem = $_.BaseName
    Write-Host "== $stem"
    claude -p "Use the indian-legal-review:review-agreement skill to review evals/cases/$($_.Name). Write the working files to ./legal-review/$stem/. Do not ask questions; this is an unattended eval run." `
        --plugin-dir . --allowedTools "Read,Write,Bash(python3:*),Bash(python:*)" | Out-Null
}
python evals\score.py --layer agent
