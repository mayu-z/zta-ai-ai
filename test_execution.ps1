$ErrorActionPreference = 'Stop'
$base = 'http://localhost:8000'
$tenant = '00000000-0000-0000-0000-000000000001'

$agents = (Invoke-RestMethod -Uri "$base/system/agents" -Method Get).items

$enableResults = @()
foreach ($a in $agents) {
  $id = $a.agent_id
  try {
    $res = Invoke-WebRequest -Uri "$base/admin/agents/$id/enable?tenant_id=$tenant" -Method Put -UseBasicParsing
    $enableResults += [pscustomobject]@{agent_id=$id; http=$res.StatusCode}
  } catch {
    $code = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { -1 }
    $enableResults += [pscustomobject]@{agent_id=$id; http=$code}
  }
}

$personas = @('student','staff','faculty','admin','system','compliance')
$execResults = @()
foreach ($p in $personas) {
  $candidate = $agents | Where-Object { $_.allowed_personas -contains $p } | Select-Object -First 1
  if (-not $candidate) {
    $execResults += [pscustomobject]@{persona=$p; query='(no agent supports persona)'; http='SKIP'; status='SKIP'; state='SKIP'; summary='No supported agent found'}
    continue
  }
  $query = [string]$candidate.name
  $payload = @{
    query = $query
    tenant_id = $tenant
    user_context = @{
      user_id = "$p-rough-e2e"
      tenant_id = $tenant
      persona = $p
      department = 'qa'
    }
  } | ConvertTo-Json -Depth 6

  try {
    $res = Invoke-WebRequest -Uri "$base/execute" -Method Post -ContentType 'application/json' -Body $payload -UseBasicParsing
    $obj = $res.Content | ConvertFrom-Json
    $execResults += [pscustomobject]@{persona=$p; query=$query; http=$res.StatusCode; status=$obj.status; state=$obj.state; summary=$obj.output_summary}
  } catch {
    $code = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { -1 }
    $execResults += [pscustomobject]@{persona=$p; query=$query; http=$code; status='ERROR'; state='ERROR'; summary=$_.Exception.Message}
  }
}

# Negative persona check
$badPayload = @{
  query = 'Leave Balance'
  tenant_id = $tenant
  user_context = @{
    user_id = 'guest-rough-e2e'
    tenant_id = $tenant
    persona = 'guest'
    department = 'qa'
  }
} | ConvertTo-Json -Depth 6

try {
  $res = Invoke-WebRequest -Uri "$base/execute" -Method Post -ContentType 'application/json' -Body $badPayload -UseBasicParsing
  $obj = $res.Content | ConvertFrom-Json
  $execResults += [pscustomobject]@{persona='guest'; query='Leave Balance'; http=$res.StatusCode; status=$obj.status; state=$obj.state; summary=$obj.output_summary}
} catch {
  $code = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { -1 }
  $execResults += [pscustomobject]@{persona='guest'; query='Leave Balance'; http=$code; status='ERROR'; state='ERROR'; summary=$_.Exception.Message}
}

Write-Output 'ENABLE_RESULTS:'
$enableResults | Format-Table -AutoSize | Out-String | Write-Output
Write-Output 'EXEC_RESULTS:'
$execResults | Format-Table -AutoSize | Out-String | Write-Output

@{ enable = $enableResults; execute = $execResults } | ConvertTo-Json -Depth 6
