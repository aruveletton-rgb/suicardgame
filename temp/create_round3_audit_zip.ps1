$ErrorActionPreference = 'Stop'
$root = (Get-Location).Path
$listPath = Join-Path $root 'temp/round3-evidence-list.txt'
$outPath = Join-Path $root 'artifacts/SUICARDGAME_AUDIT_EVIDENCE_20260929_ROUND3.zip'
if (Test-Path -LiteralPath $outPath) { Remove-Item -LiteralPath $outPath -Force }
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$items = @(Get-Content -LiteralPath $listPath | Where-Object { $_.Trim() -ne '' })
$seen = New-Object 'System.Collections.Generic.HashSet[string]'
$archive = [System.IO.Compression.ZipFile]::Open($outPath, [System.IO.Compression.ZipArchiveMode]::Create)
try {
  foreach ($rel in $items) {
    $full = Join-Path $root $rel
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { throw "Missing evidence file: $rel" }
    $entryName = $rel.Replace('\','/')
    if (-not $seen.Add($entryName)) { throw "Duplicate evidence entry: $entryName" }
    [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $full, $entryName, [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
  }
  $listEntry = $archive.CreateEntry('round3-evidence-list.txt', [System.IO.Compression.CompressionLevel]::Optimal)
  $stream = $listEntry.Open()
  try {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes((Get-Content -Raw -LiteralPath $listPath))
    $stream.Write($bytes, 0, $bytes.Length)
  } finally { $stream.Dispose() }
} finally { $archive.Dispose() }
$sha = (Get-FileHash -Algorithm SHA256 -LiteralPath $outPath).Hash.ToLowerInvariant()
$size = (Get-Item -LiteralPath $outPath).Length
"created=$outPath"
"members=$($seen.Count + 1)"
"bytes=$size"
"sha256=$sha"
