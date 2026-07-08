"""Spoken-punctuation ("Diktatmodus") post-processing.

When enabled, spoken German command words are turned into the actual marks —
the standard way professional dictation works, and the only way to produce
marks that cannot be inferred from audio (parentheses, colons, semicolons,
dashes, quotation marks).

    "Ach Komma du meine Güte Punkt"  ->  "Ach, du meine Güte."

Two design points make this reliable:

* **Only the exact singular command form is a command.** ``Komma`` becomes
  ``,`` but the content word ``Kommas`` (plural) is left untouched — so a
  mixed sentence like "ein Text mit Doppelpunkt Kommas Semikolon Punkten"
  correctly yields "ein Text mit: Kommas; Punkten".
* Spacing and capitalization are rebuilt from scratch around the inserted
  marks, so the output reads naturally regardless of where Whisper placed
  its own (now redundant) punctuation — the German normalizer, which runs
  after this stage, collapses any leftover duplicates.

Opt-in only (``TranscribeOptions.dictation_mode``): it reinterprets common
words, so it must never run on normal, non-dictated speech.
"""

from __future__ import annotations

import re

from engine.types import Segment, TranscriptResult

# The ASR splits long compound command words unpredictably (e.g.
# "Ausrufezeichen" -> "Ausrufe Zeichen"). Glue the known splits back together
# before matching, so the command is recognized either way.
_SPLIT_COMPOUNDS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bausrufe\s+zeichen\b", re.IGNORECASE), "Ausrufezeichen"),
    (re.compile(r"\bfrage\s+zeichen\b", re.IGNORECASE), "Fragezeichen"),
    (re.compile(r"\banführungs\s+zeichen\b", re.IGNORECASE), "Anführungszeichen"),
    (re.compile(r"\bdoppel\s+punkt\b", re.IGNORECASE), "Doppelpunkt"),
    (re.compile(r"\bgedanken\s+strich\b", re.IGNORECASE), "Gedankenstrich"),
    (re.compile(r"\bbinde\s+strich\b", re.IGNORECASE), "Bindestrich"),
    (re.compile(r"\bstrich\s+punkt\b", re.IGNORECASE), "Strichpunkt"),
    (re.compile(r"\bauslassungs\s+punkte\b", re.IGNORECASE), "Auslassungspunkte"),
]

# exact single-word commands (matched case-insensitively, whole token only)
_SINGLE: dict[str, str] = {
    "komma": ",",
    "punkt": ".",
    "fragezeichen": "?",
    "ausrufezeichen": "!",
    "doppelpunkt": ":",
    "semikolon": ";",
    "strichpunkt": ";",
    "bindestrich": "-",
    "minus": "-",
    "gedankenstrich": "–",
    "auslassungspunkte": "…",
}

# two-word commands
_DOUBLE: dict[tuple[str, str], str] = {
    ("klammer", "auf"): "(",
    ("klammer", "zu"): ")",
    ("anführungszeichen", "auf"): "„",
    ("anführungszeichen", "zu"): "“",
    ("neue", "zeile"): "\n",
    ("neuer", "absatz"): "\n",
}

# per-mark (space_before, space_after) — words default to (True, True)
_SPACING: dict[str, tuple[bool, bool]] = {
    ",": (False, True),
    ".": (False, True),
    "?": (False, True),
    "!": (False, True),
    ":": (False, True),
    ";": (False, True),
    ")": (False, True),
    "“": (False, True),
    "…": (False, True),
    "(": (True, False),
    "„": (True, False),
    "-": (False, False),
    "–": (True, True),
    "\n": (False, False),
}

_SENTENCE_ENDERS = ".!?\n"

# Whisper attaches its own inferred punctuation to words, especially around
# the pauses a speaker makes near a dictated command ("Gedankenstrich" spoken
# with pauses becomes ", Gedankenstrich,"). In dictation mode ALL punctuation
# comes from the spoken commands, so this outer punctuation is stripped from
# every token — both to make commands match, and to drop Whisper's now-stray
# marks. Internal characters (hyphens in "E-Mail", the comma in "3,5") are
# left untouched because ``str.strip`` only removes leading/trailing chars.
_OUTER_PUNCT = ",.;:!?…\"„“”«»()[]"


class DictationCommands:
    """Convert spoken German punctuation words into marks."""

    def apply(self, text: str) -> str:
        for pattern, joined in _SPLIT_COMPOUNDS:
            text = pattern.sub(joined, text)
        # core = token without Whisper's own outer punctuation
        cores = [token.strip(_OUTER_PUNCT) for token in text.split()]
        # atoms: (text, space_before, space_after)
        atoms: list[tuple[str, bool, bool]] = []
        i = 0
        while i < len(cores):
            core = cores[i]
            if not core:
                i += 1
                continue  # token was pure Whisper punctuation — drop it
            low = core.lower()
            pair = (low, cores[i + 1].lower()) if i + 1 < len(cores) else None
            if pair is not None and pair in _DOUBLE:
                mark = _DOUBLE[pair]
                atoms.append((mark, *_SPACING[mark]))
                i += 2
            elif low in _SINGLE:
                mark = _SINGLE[low]
                atoms.append((mark, *_SPACING[mark]))
                i += 1
            else:
                atoms.append((core, True, True))
                i += 1

        out: list[str] = []
        prev_space_after = False
        for idx, (token, space_before, space_after) in enumerate(atoms):
            if idx > 0 and prev_space_after and space_before:
                out.append(" ")
            out.append(token)
            prev_space_after = space_after
        return self._recapitalize("".join(out).strip())

    @staticmethod
    def _recapitalize(text: str) -> str:
        chars = list(text)
        capitalize = True
        for idx, ch in enumerate(chars):
            if capitalize and ch.isalpha():
                chars[idx] = ch.upper()
                capitalize = False
            elif ch in _SENTENCE_ENDERS:
                capitalize = True
            elif not ch.isspace():
                capitalize = False
        return "".join(chars)

    def process(self, result: TranscriptResult) -> TranscriptResult:
        segments = [
            Segment(
                id=seg.id,
                start=seg.start,
                end=seg.end,
                text=self.apply(seg.text),
                words=seg.words,
                speaker=seg.speaker,
            )
            for seg in result.segments
        ]
        return TranscriptResult(segments=segments, info=result.info)
