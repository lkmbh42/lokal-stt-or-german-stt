# Manual Test Checklist — Variant A (Desktop)

Run against `python run.py` with a real model (default `large-v3`; `base` is
fine for functional passes). Automated coverage (engine 84, backend 38,
frontend 26 tests + axe gate) runs separately — this list covers what
automation can't.

## Launch & packaging

- [ ] `python run.py` starts, prints the URL, opens the default browser.
- [ ] `python run.py --port 0` picks a free port; app fully works there.
- [ ] `python run.py --no-browser` stays headless; URL reachable manually.
- [ ] Server refuses non-loopback `host:` in config.yaml with a clear error.
- [ ] Second start while running: clear port-in-use error, no data corruption.
- [ ] `Ctrl+C` shuts down cleanly; restart sees previous job history (SQLite).

## Batch transcription

- [ ] Upload each supported container once: mp3, wav, m4a, mp4, flac → all complete.
- [ ] Upload two files in one submit → two jobs, both complete, list newest-first.
- [ ] Progress percentage moves during a long file (> 1 min audio).
- [ ] Cancel a processing job → status "Abgebrochen", worker takes the next job.
- [ ] Unsupported extension rejected with German error before any processing.
- [ ] File larger than `max_upload_mb` rejected (413) with clear message.
- [ ] `initial_prompt`/hotwords demonstrably bias recognition (proper noun test).
- [ ] All six export links download; `.zip` contains all five formats; umlauts
      correct in every format (open .txt as UTF-8, .docx in Word).
- [ ] Delete removes the job **and** its files under `data/`.

## Live recording

- [ ] Recording starts within ~2 s of activation; partial text appears and
      stabilizes into committed sentences at pauses.
- [ ] Save-checkbox on: after stop, a job "aufnahme-…" appears and completes
      with noticeably better text than the live view (full-quality pass).
- [ ] Save-checkbox off: stop produces no history entry.
- [ ] Mic permission denied → specific error, app recovers without reload.
- [ ] Reload mid-recording → server side session ends without crash (check log).
- [ ] Long recording (> 5 min) stays responsive; memory does not balloon
      (rolling window commits keep the pending buffer bounded).

## Offline guarantee

- [ ] With weights pre-staged and `local_files_only: true`: disable the
      network adapter → upload + live + export all work identically.
- [ ] With `local_files_only: true` and *missing* weights: startup job fails
      with an explicit "model not found" error, no download attempt (verify
      no outbound connections with `netstat`/firewall log).

## Accessibility

- [ ] Execute the full [NVDA walkthrough](a11y-walkthrough-desktop.md) (A–F) — separate artifact, gates sign-off.
- [ ] Zoom 200 %: no loss of content or function (WCAG 1.4.4).
- [ ] Windows High-Contrast mode: focus indicator and all text visible.
- [ ] `prefers-reduced-motion`: no animations (there are none by design — verify none regress in).
