# Verified Windows candidate: BOOM identification

This is a controlled, unsigned Windows test candidate. Its download integrity was independently checked; signing, installed state, and hardware behavior remain unqualified. Do not combine its metadata or hashes with earlier PR candidates.

## Candidate identity

| Item | Value |
| --- | --- |
| Desktop workflow | [41378220256](https://github.com/colinatwood/stagemesh/actions/runs/41378220256) |
| Source | `b2c4d34a6e808fd378ae63649adbe905ac43e086` |
| Windows online artifact | [13112880809](https://github.com/colinatwood/stagemesh/actions/runs/41378220256/artifacts/13112880809) |
| ZIP SHA-256 | `02e60cdb2ae61dc227e1d11d089fd26e0d334a6bef4b1ebc2ad29a215be3c02e` |
| MSI SHA-256 | `b3d51933f28de5352d8a60efe1fd55f5410a412ce3927dbab4837ac64f8aa07d` |
| MSI installed-executable reference | `f4ba8538eebaf4b4f9ac17add5ce2edec00522d461572a5a1d2864cc35336971` |
| Index artifact | [13112901158](https://github.com/colinatwood/stagemesh/actions/runs/41378220256/artifacts/13112901158) |
| Index ZIP SHA-256 | `576ea1176546ce9a149c13eb96f3abe88cbc7bc0adee3727229d5779fef8d7f9` |

The candidate includes merged #188 (friendly names), #186 (earlier verification record), and #185 (CI dependency update). It predates diagnostic-only #190. The Windows verifier passed 11 files. Its manifest, checksum list, and signing-verification report matched the downloaded release index. Other platform bundles were not independently rechecked in this pass. See [the recorded evidence](https://github.com/colinatwood/stagemesh/issues/189#issuecomment-6568400500).

## 1. Verify the download

Download the Windows online artifact above. Set the actual ZIP path below; GitHub may choose a different filename. Python 3 must already be available as `py -3`. These commands verify and extract files only.

```powershell
$zip = Read-Host "Full path to downloaded artifact ZIP"
$expectedZip = "02e60cdb2ae61dc227e1d11d089fd26e0d334a6bef4b1ebc2ad29a215be3c02e"
if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedZip) {
    throw "ZIP hash mismatch; stop."
}

$bundle = Join-Path $env:USERPROFILE "Downloads\StageMesh-13112880809"
if (Test-Path -LiteralPath $bundle) {
    throw "Destination already exists; use a new empty destination."
}
Expand-Archive -LiteralPath $zip -DestinationPath $bundle
Set-Location -LiteralPath $bundle
py -3 .\verify-download.py --directory .
if ($LASTEXITCODE -ne 0) { throw "Bundle verification failed; stop." }

$msi = Join-Path $bundle "msi\StageMesh_0.1.0_x64_en-US.msi"
$expectedMsi = "b3d51933f28de5352d8a60efe1fd55f5410a412ce3927dbab4837ac64f8aa07d"
if ((Get-FileHash -LiteralPath $msi -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedMsi) {
    throw "MSI hash mismatch; stop."
}
```

A hash match establishes consistency with the recorded candidate, not publisher authentication. Do not bypass Windows security policy.

## 2. Install only with explicit operator authorization

The verification commands above do not authorize installation or replacement. After authorization, close StageMesh, preserve existing work, and run the verified MSI through the normal interactive installer. Record the result and actual installed executable path privately. Do not uninstall, alter drivers or change Windows/Apogee device settings to make this test pass.

## 3. Compare the selected installed executable

From the same verified bundle directory, enter the actual executable path. Do not guess the installation directory or use a copied executable from the downloaded bundle.

```powershell
$installed = Read-Host "Full path to installed stagemesh-desktop.exe"
py -3 .\verify-installed-executable.py check --directory . --executable $installed --installer "msi/StageMesh_0.1.0_x64_en-US.msi" --commit b2c4d34a6e808fd378ae63649adbe905ac43e086 --distribution-channel online
if ($LASTEXITCODE -ne 0) { throw "Installed candidate comparison failed; stop." }
```

Preserve comparison output outside the bundle. A match compares one executable with the producer's extracted MSI payload reference. It does not qualify installed sidecars/resources, publisher identity, clean-host behavior, or hardware.

## 4. Identify BOOM before activation

Open Setup with capture stopped and physical playback/lighting outputs disarmed. Refresh detection and inspect both input and output lists. Confirm the intended BOOM endpoint is recognizable as `2 - Apogee BOOM` (or its current Windows friendly name). Duplicate names may carry a short identity suffix; missing names carry a fallback plus suffix. Record the observed labels privately.

Do not select another endpoint merely to complete the exercise. If BOOM is absent or ambiguous, keep capture stopped and record the failure. Do not start capture or playback during this identification step.

## 5. Continue supervised acceptance

After the candidate comparison and BOOM identification pass, follow [the existing three-cycle recovery protocol](capture-recovery-app-qualification.md) with participant assistance. Keep route gain zero and outputs disarmed; each activation must be explicit. Quality measurements, screen-reader acceptance and the seven clean-host tracks remain separate requirements in [the release tracker](https://github.com/colinatwood/stagemesh/issues/189). This existing PC is not automatically a clean-host environment.
