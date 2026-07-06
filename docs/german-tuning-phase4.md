# German Post-Processing Tuning Pass (Phase 4)

Method: seven number/date/currency/vocabulary-heavy German sentences,
synthesized locally (SAPI de-DE voice, 16 kHz), transcribed with the real
engine (`base` model, CPU) — raw output compared against the normalizer and
against vocabulary injection. All outputs below are actual engine output
from 2026-07-06, reproducible via the corpus sentences listed here.

## Finding 1 — Whisper's native German number formatting is already correct

| Spoken | Raw engine output |
|---|---|
| „dreihundertfünfundvierzig Euro und zwanzig Cent" | `345 Euro und 20 Cent` |
| „zwei Komma fünf Kilogramm … neunzehn Euro neunzig" | `2,5 kg … 19,90 Euro` |
| „eine Million zweihunderttausend Euro" | `eine Million 200.000 Euro` |
| „drei Komma fünf Prozent auf einundzwanzig Prozent" | `3,5 Prozent auf 21 Prozent` |
| „am dritten Oktober … um vierzehn Uhr dreißig" | `am 3. Oktober … um 14 Uhr 30` |
| „zum Beispiel … Herrn Doktor Müller" | `zum Beispiel … Herrn Dr. Müller` |

Decimal comma, German thousands grouping (`200.000`), ordinal dates and
abbreviations all arrive correctly formatted. **Consequence:** the Phase 0
decision to keep `GermanNormalizer` conservative is validated — the opt-in
`decimal_comma` / `thousands_grouping` rewrites changed *nothing* on this
corpus and stay off by default (they remain available as a safety net for
fine-tuned checkpoints with different output conventions).

One error in the corpus was a recognition (WER) issue, not formatting:
`zweitausendsechsundzwanzig` → `2006` with the `base` model. Model-size
dependent; re-check with `large-v3` on the production host.

## Finding 2 — vocabulary injection works, but the mechanisms differ

Sentence: „Die Besprechung mit der Firma **Anthropic** findet über
Kubernetes statt."

| Configuration | Output |
|---|---|
| no boost | `…Firma Antropik…` (misspelled) |
| `hotwords="Anthropic Kubernetes"` | `…Firma Anthropic…` ✓ clean |
| `initial_prompt` + default conditioning | correct name, but **sentence duplicated** (prompt echo) |
| `initial_prompt` only, conditioning off | `Antropik` **plus a hallucinated sentence** |

**Consequences (implemented):**

1. **Engine change:** when `initial_prompt` is set and the caller left
   `condition_on_previous_text` at its default, the engine now disables
   conditioning automatically (explicit caller choice always wins). This
   removes the prompt-echo duplication class. Regression-tested in
   `engine/tests/test_transcriber.py::TestPromptConditioningInteraction`.
2. **Guidance:** prefer **hotwords** for names/terms — strongest effect, no
   hallucination risk observed. Use `initial_prompt` for stylistic/context
   priming, ideally together with hotwords. Both UIs expose the fields; this
   note is the operator guidance.

## Regression corpus

The seven sentences above are the living tuning corpus. Re-run after any
model swap (they take ~1 min on CPU with `base`):
synthesize via `engine/scripts/make_fixtures.py`-style SAPI calls or record
them, transcribe with `python -m engine.transcribe <wav> --lang de`, and
compare against the tables here.
