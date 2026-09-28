# Renders the fictional English utterances used by the M2 latency benchmark into WAV files.
#
#   pwsh -NoProfile -ExecutionPolicy Bypass -File scripts\make-benchmark-audio.ps1
#
# Uses only the speech voices that ship with Windows (System.Speech); nothing is downloaded or
# installed. Output: runtime\bench-audio\<voice>-<nn>.wav (16 kHz, 16-bit, mono) plus
# utterances.json with the reference text. runtime\ is outside Git. This is synthetic speech for
# timing, not a speech-recognition accuracy test: no Hindi voice is installed, and real Hindi and
# English recordings are a human task (H5).

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$Out = Join-Path $Repo "runtime\bench-audio"
New-Item -ItemType Directory -Force $Out | Out-Null

$Utterances = @(
    "Yesterday some men from the village came to our house and shouted at us.",
    "They told my husband to withdraw the complaint or face consequences.",
    "We are staying with my sister now in the next village.",
    "My son was hurt on his arm and we went to the hospital.",
    "The police at the station did not write our report.",
    "Nobody in the village is talking to us since the complaint.",
    "They stopped us from taking water from the hand pump.",
    "I am scared they will come back again.",
    "My phone is with me and I can talk now.",
    "The village head was also there when this happened.",
    "It started two weeks ago after the land dispute.",
    "Please tell me what happens next with my case."
)
$Voices = @("Microsoft Heera", "Microsoft Ravi")

Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$installed = $synth.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }
# The Indian-English voices are visible from PowerShell 7 (pwsh); Windows PowerShell 5.1 may list only
# the desktop voices. Fall back to two installed English voices rather than failing.
if (-not ($Voices | Where-Object { $installed -contains $_ })) {
    $Voices = @($synth.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like "en-*" } |
        ForEach-Object { $_.VoiceInfo.Name } | Select-Object -First 2)
    Write-Warning "Indian-English voices not visible here; using: $($Voices -join ', ') (run with pwsh for en-IN)"
}
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000,
    [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)

$manifest = @()
foreach ($voice in $Voices) {
    if ($installed -notcontains $voice) { Write-Warning "$voice is not installed; skipped"; continue }
    $synth.SelectVoice($voice)
    $tag = ($voice -replace "Microsoft ", "").ToLower()
    for ($i = 0; $i -lt $Utterances.Count; $i++) {
        $name = "{0}-{1:D2}.wav" -f $tag, ($i + 1)
        $synth.SetOutputToWaveFile((Join-Path $Out $name), $format)
        $synth.Speak($Utterances[$i])
        $synth.SetOutputToNull()
        $manifest += [ordered]@{ file = $name; voice = $voice; index = $i + 1; text = $Utterances[$i] }
    }
}
$synth.Dispose()
$manifest | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $Out "utterances.json")
Write-Output "wrote $($manifest.Count) files to runtime\bench-audio"
