# German Model Benchmark — large-v3-turbo vs. German fine-tune

**Question:** does a German fine-tuned Whisper beat the default
`large-v3-turbo` on German audio, enough to switch the deployed model?

**Short answer: no — keep `large-v3-turbo`.** The German fine-tune
(`primeline/whisper-large-v3-turbo-german`) is at best a wash: marginally
better in heavy noise, marginally *worse* on clean audio, and it changes
German spelling conventions (ß→ss). The differences are within sampling
noise. The custom-vocabulary dictionary we already ship is a more reliable,
targeted accuracy lever for the names/terms that actually matter.

## Method

10 natural German sentences (names, places, umlauts, everyday vocabulary; no
spelled-out numbers, to avoid digit/word confounds), synthesized with the
Windows SAPI de-DE voice so ground truth is exact and the whole benchmark is
reproducible offline. WER on normalized text (lowercase, punctuation
stripped) — standard practice. Reproduce:

```
# clean
python engine/scripts/benchmark.py --models large-v3-turbo,<other>
# hard (background noise as loud as the speech)
python engine/scripts/benchmark.py --models large-v3-turbo,<other> --noise-snr 0
```

The German fine-tune was converted to CTranslate2 with
`ct2-transformers-converter` (see docs/model-management.md); `tokenizer.json`
and `preprocessor_config.json` were copied from the base turbo model (a
fine-tune shares the base tokenizer).

## Results (mean WER over 10 sentences)

| Model | Clean | SNR 5 dB | SNR 0 dB (hard) | Speed |
|---|---|---|---|---|
| **large-v3-turbo** (current default) | **0.0 %** | 0.0 % | 5.3 % | ~19 s/sentence CPU |
| **turbo-german** (primeline fine-tune) | 1.0 % | — | **4.5 %** | same |

Per-sentence at 0 dB, they mostly tie; the fine-tune won "bedienen" (turbo
heard "verdienen") and "hier" (turbo heard "mir"), while turbo kept "Straße"
where the fine-tune wrote "Strasse".

## Reading the numbers

1. **On clean German — the tool's normal case — turbo is already perfect
   (0 %).** There is no headroom for any model to improve. This is the single
   most important result: for ordinary dictation, the current model cannot be
   beaten on accuracy.
2. **The fine-tune's clean 1.0 % is a spelling artifact,** not a recognition
   error: it renders ß as "ss" (valid German, but strict WER counts it as a
   substitution). Depending on your house style this is neutral or a mild
   negative.
3. **In heavy noise the fine-tune edges ahead (4.5 % vs 5.3 %)** — a ~0.8-point
   / ~15 % relative gain, but on a 10-sentence sample that is within noise and
   not decisive.
4. **No speed difference** — same turbo architecture.

## Recommendation

- **Keep `large-v3-turbo` as the deployed default.** The fine-tune is not a
  clear win and adds operational cost (a converted model to maintain) plus a
  spelling change.
- **Use the custom dictionary** (Wörterbuch) for the accuracy that actually
  matters day to day — names, places, domain terms. That is targeted and
  reliable, unlike a whole-model swap that trades wins.
- **Re-evaluate only with real audio.** This benchmark is clean, single-voice
  synthetic speech — a lower bound on where a fine-tune helps. If your team
  works with genuinely hard audio (strong accents, phone lines, cross-talk),
  run `benchmark.py` on **your own recordings with corrected transcripts**
  (the editor/correction workflow produces exactly those ground-truth pairs).
  If the fine-tune shows a clear, consistent win there, switching is a
  one-line config change:
  `STT_ENGINE__MODEL=/models/whisper-large-v3-turbo-german-ct2`.

## Note

`torch` + `transformers` were installed only to *convert* the fine-tune for
this evaluation. They are **not** runtime dependencies — the app and the
Docker images use faster-whisper / CTranslate2 only.
