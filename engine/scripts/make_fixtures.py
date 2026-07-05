"""Generate audio test fixtures locally — no downloads, no cloud.

Creates in ``engine/tests/fixtures/``:

* ``silence.wav``        — 3 s of digital silence (VAD should yield nothing)
* ``tone.wav``           — 2 s 440 Hz sine (non-speech; VAD should yield nothing)
* ``german_sample.wav``  — real German speech synthesized with the Windows
  SAPI de-DE voice (e.g. Microsoft Hedda). On non-Windows hosts, or when no
  German voice is installed, this file is skipped and the script tells you to
  provide any short German WAV under the same name (model-marked tests skip
  when it is absent).

Run: ``python engine/scripts/make_fixtures.py``
"""

from __future__ import annotations

import math
import struct
import subprocess
import sys
import wave
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
SAMPLE_RATE = 16_000

GERMAN_TEXT = (
    "Guten Tag. Dies ist ein Test der deutschen Spracherkennung. "
    "Wir prüfen die Übertragung von Umlauten und Zahlen, "
    "zum Beispiel einundzwanzig und der fünfte Juli."
)

# PowerShell + System.Speech: pick a de-DE voice, write 16 kHz 16-bit mono WAV.
_SAPI_TEMPLATE = r"""
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice = $synth.GetInstalledVoices() | Where-Object {{ $_.VoiceInfo.Culture.Name -eq 'de-DE' -and $_.Enabled }} | Select-Object -First 1
if (-not $voice) {{ Write-Error 'no de-DE voice installed'; exit 3 }}
$synth.SelectVoice($voice.VoiceInfo.Name)
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$synth.SetOutputToWaveFile('{out_path}', $fmt)
$synth.Speak('{text}')
$synth.Dispose()
"""


def write_wav(path: Path, samples: list[int]) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(struct.pack(f"<{len(samples)}h", *samples))


def make_silence(path: Path, seconds: float = 3.0) -> None:
    write_wav(path, [0] * int(SAMPLE_RATE * seconds))


def make_tone(path: Path, seconds: float = 2.0, freq: float = 440.0) -> None:
    n = int(SAMPLE_RATE * seconds)
    samples = [int(12000 * math.sin(2 * math.pi * freq * i / SAMPLE_RATE)) for i in range(n)]
    write_wav(path, samples)


def make_german_speech(path: Path) -> bool:
    if sys.platform != "win32":
        return False
    script = _SAPI_TEMPLATE.format(out_path=str(path), text=GERMAN_TEXT.replace("'", "''"))
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        print(proc.stderr.strip(), file=sys.stderr)
        return False
    return path.is_file() and path.stat().st_size > 1000


def main() -> int:
    FIXTURES.mkdir(parents=True, exist_ok=True)

    make_silence(FIXTURES / "silence.wav")
    print(f"wrote {FIXTURES / 'silence.wav'}")
    make_tone(FIXTURES / "tone.wav")
    print(f"wrote {FIXTURES / 'tone.wav'}")

    german = FIXTURES / "german_sample.wav"
    if make_german_speech(german):
        print(f"wrote {german} (SAPI de-DE synthesis)")
        print(f"  text: {GERMAN_TEXT}")
    else:
        print(
            "could not synthesize German speech (non-Windows host or no de-DE voice).\n"
            f"Place any short German speech WAV at {german} to enable model-marked tests.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
