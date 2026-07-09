"""German word-error-rate (WER) benchmark for comparing models.

Compares one or more models on a fixed set of German sentences with known
ground truth, and prints per-sample and aggregate WER.

    python engine/scripts/benchmark.py --models large-v3-turbo
    python engine/scripts/benchmark.py --models large-v3-turbo,./models/whisper-de

Ground truth is the text fed to the Windows SAPI de-DE voice, so the audio
is synthesized locally (no downloads, fully reproducible). This is a
*clean-speech* benchmark: TTS has no accent/noise, so absolute WER is low
and differences between strong models are small. A German fine-tune usually
shows a bigger advantage on real, harder audio — treat these numbers as a
lower bound on the benefit and cross-check with published Common Voice de
results before deciding.

WER is computed on normalized text (lowercase, punctuation stripped,
whitespace collapsed) — the standard practice, so digit-vs-word or casing
differences don't distort the score.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent.parent / "tests" / "benchmark"
SAMPLE_RATE = 16_000

# Natural German sentences (names, places, umlauts, everyday vocabulary),
# deliberately without spelled-out numbers so digit/word formatting does not
# confound the word-error rate.
SENTENCES: dict[str, str] = {
    "gruss": "Guten Morgen, Frau Schäfer, schön, dass Sie heute vorbeikommen.",
    "termin": "Der nächste Termin findet am Donnerstag in unserem Büro in Marburg statt.",
    "wetter": "Am Wochenende soll es regnen, deshalb nehmen wir die Regenjacken mit.",
    "arbeit": "Nach der Besprechung schicke ich Ihnen das Protokoll per E-Mail zu.",
    "reise": "Wir fahren mit dem Zug über Frankfurt und steigen in Kassel um.",
    "familie": "Meine Tochter besucht seit September die Grundschule in unserer Straße.",
    "gesundheit": "Bitte nehmen Sie die Tabletten zweimal täglich nach dem Essen ein.",
    "technik": "Das neue Gerät lässt sich einfach bedienen und spart viel Zeit.",
    "brief": "Sehr geehrte Damen und Herren, vielen Dank für Ihre freundliche Anfrage.",
    "alltag": "Könnten Sie mir bitte sagen, wo hier die nächste Apotheke ist?",
}

_SAPI = r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$v = $s.GetInstalledVoices() | Where-Object {{ $_.VoiceInfo.Culture.Name -eq 'de-DE' -and $_.Enabled }} | Select-Object -First 1
if (-not $v) {{ Write-Error 'no de-DE voice'; exit 3 }}
$s.SelectVoice($v.VoiceInfo.Name)
$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$s.SetOutputToWaveFile('{out}', $f)
$s.Speak('{text}')
$s.Dispose()
"""


def synthesize() -> bool:
    if sys.platform != "win32":
        print("SAPI synthesis is Windows-only; provide WAVs manually.", file=sys.stderr)
        return False
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in SENTENCES.items():
        path = BENCH_DIR / f"{name}.wav"
        if path.is_file():
            continue
        script = _SAPI.format(out=str(path), text=text.replace("'", "''"))
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            print(proc.stderr.strip(), file=sys.stderr)
            return False
    return True


def make_noisy(snr_db: float) -> Path:
    """Create white-noise-degraded copies at the given SNR; return their dir.

    Clean TTS saturates strong models at ~0% WER, so a robustness test needs
    harder audio. A fixed random seed keeps it reproducible.
    """
    import wave

    import numpy as np

    out_dir = BENCH_DIR / f"noisy_snr{int(snr_db)}"
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(1234)
    for name in SENTENCES:
        src = BENCH_DIR / f"{name}.wav"
        dst = out_dir / f"{name}.wav"
        if dst.is_file() or not src.is_file():
            continue
        with wave.open(str(src), "rb") as w:
            params = w.getparams()
            signal = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64)
        rms = np.sqrt(np.mean(signal**2)) or 1.0
        noise = rng.normal(0.0, rms / (10 ** (snr_db / 20)), len(signal))
        noisy = np.clip(signal + noise, -32768, 32767).astype(np.int16)
        with wave.open(str(dst), "wb") as w:
            w.setparams(params)
            w.writeframes(noisy.tobytes())
    return out_dir


def normalize(text: str) -> list[str]:
    out = []
    for ch in text.lower():
        if ch.isalnum() or ch.isspace():
            out.append(ch)
        else:
            out.append(" ")
    return "".join(out).split()


def wer(reference: str, hypothesis: str) -> float:
    ref, hyp = normalize(reference), normalize(hypothesis)
    if not ref:
        return 0.0
    # Levenshtein distance over word lists
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i]
        for j, h in enumerate(hyp, 1):
            cost = 0 if r == h else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1] / len(ref)


def run_model(model: str, device: str, audio_dir: Path) -> dict[str, tuple[str, float]]:
    from engine import EngineConfig, TranscribeOptions, Transcriber

    engine = Transcriber(EngineConfig(model=model, device=device))
    # normalization off: WER normalizes anyway, and we want raw recognition
    options = TranscribeOptions(normalize_german=False)
    results: dict[str, tuple[str, float]] = {}
    for name, reference in SENTENCES.items():
        path = audio_dir / f"{name}.wav"
        if not path.is_file():
            continue
        text = engine.transcribe(path, options).text.replace("\n", " ").strip()
        results[name] = (text, wer(reference, text))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--models", required=True, help="Comma-separated model names or local CT2 paths"
    )
    parser.add_argument("--device", default="auto")
    parser.add_argument(
        "--noise-snr",
        type=float,
        default=None,
        help="Benchmark on white-noise-degraded audio at this SNR in dB (lower = harder)",
    )
    parser.add_argument("--show-text", action="store_true", help="Print each transcript")
    args = parser.parse_args()

    if not synthesize():
        return 1
    audio_dir = BENCH_DIR
    if args.noise_snr is not None:
        audio_dir = make_noisy(args.noise_snr)
        print(f"Benchmarking noise-degraded audio at SNR {args.noise_snr:.0f} dB")
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    per_model: dict[str, dict[str, tuple[str, float]]] = {}
    timings: dict[str, float] = {}
    for model in models:
        print(f"\n### {model}")
        started = time.perf_counter()
        per_model[model] = run_model(model, args.device, audio_dir)
        timings[model] = time.perf_counter() - started

    print("\n=== WER per sentence (%) ===")
    header = "sentence".ljust(14) + "".join(m[:22].rjust(24) for m in models)
    print(header)
    for name in SENTENCES:
        row = name.ljust(14)
        for model in models:
            row += f"{per_model[model][name][1] * 100:23.1f} " if name in per_model[model] else ""
        print(row)

    print("\n=== Aggregate ===")
    for model in models:
        scores = [v[1] for v in per_model[model].values()]
        avg = sum(scores) / len(scores) if scores else 0.0
        print(f"{model[:40]:40}  mean WER {avg * 100:5.1f}%   ({timings[model]:.0f}s total)")

    if args.show_text:
        print("\n=== Transcripts ===")
        for name, reference in SENTENCES.items():
            print(f"\n[{name}] REF: {reference}")
            for model in models:
                if name in per_model[model]:
                    print(f"  {model[:24]:24}: {per_model[model][name][0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
