"""Spoken-punctuation ("Diktatmodus") post-processing.

When enabled, spoken German command words are turned into the actual marks —
the standard way professional dictation works, and the only way to produce
marks that cannot be inferred from audio (parentheses, colons, semicolons,
dashes, quotation marks, …).

    "Ach Komma du meine Güte Punkt"  ->  "Ach, du meine Güte."

Design points that make it reliable:

* **Only the exact singular command form is a command.** ``Komma`` becomes
  ``,`` but the content word ``Kommas`` (plural) is left untouched — so a
  mixed sentence like "ein Text mit Doppelpunkt Kommas Semikolon Punkten"
  correctly yields "ein Text mit: Kommas; Punkten".
* **Whisper's own punctuation is stripped.** Natural pauses make the ASR wrap
  command words in inferred commas (", Gedankenstrich,"); in dictation mode
  all punctuation comes from the spoken commands, so this outer punctuation is
  removed before matching and does not survive.
* **Longest command wins** — three-word commands ("eckige Klammer auf") are
  matched before two-word ("Klammer auf") before single words.
* Spacing and capitalization are rebuilt from scratch, and split compounds the
  ASR produces ("Ausrufe Zeichen") are glued back together first.

Opt-in only (``TranscribeOptions.dictation_mode``): it reinterprets common
words, so it must never run on normal, non-dictated speech.
"""

from __future__ import annotations

import re

from engine.types import Segment, TranscriptResult

# The ASR splits long compound command words unpredictably (e.g.
# "Ausrufezeichen" -> "Ausrufe Zeichen"). Glue known splits back together
# before matching, so the command is recognized either way.
_SPLIT_COMPOUNDS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bausrufe\s+zeichen\b", re.IGNORECASE), "Ausrufezeichen"),
    (re.compile(r"\bausrufungs\s+zeichen\b", re.IGNORECASE), "Ausrufungszeichen"),
    (re.compile(r"\bfrage\s+zeichen\b", re.IGNORECASE), "Fragezeichen"),
    (re.compile(r"\banführungs\s+zeichen\b", re.IGNORECASE), "Anführungszeichen"),
    (re.compile(r"\bgänse\s+füßchen\b", re.IGNORECASE), "Gänsefüßchen"),
    (re.compile(r"\bdoppel\s+punkt\b", re.IGNORECASE), "Doppelpunkt"),
    (re.compile(r"\bgedanken\s+strich\b", re.IGNORECASE), "Gedankenstrich"),
    (re.compile(r"\bbinde\s+strich\b", re.IGNORECASE), "Bindestrich"),
    (re.compile(r"\bstrich\s+punkt\b", re.IGNORECASE), "Strichpunkt"),
    (re.compile(r"\bschräg\s+strich\b", re.IGNORECASE), "Schrägstrich"),
    (re.compile(r"\bauslassungs\s+punkte\b", re.IGNORECASE), "Auslassungspunkte"),
    (re.compile(r"\bprozent\s+zeichen\b", re.IGNORECASE), "Prozentzeichen"),
    (re.compile(r"\bzeilen\s+umbruch\b", re.IGNORECASE), "Zeilenumbruch"),
    (re.compile(r"\bgroß\s+schreiben\b", re.IGNORECASE), "großschreiben"),
    (re.compile(r"\bklein\s+schreiben\b", re.IGNORECASE), "kleinschreiben"),
]

# Commands keyed by the tuple of lowercased word(s). Longest match wins, so a
# three-word command is preferred over its two-word prefix.
_COMMANDS: dict[tuple[str, ...], str] = {
    # sentence punctuation
    ("komma",): ",",
    ("punkt",): ".",
    ("fragezeichen",): "?",
    ("ausrufezeichen",): "!",
    ("ausrufungszeichen",): "!",
    ("doppelpunkt",): ":",
    ("semikolon",): ";",
    ("strichpunkt",): ";",
    ("auslassungspunkte",): "…",
    # dashes and slashes
    ("bindestrich",): "-",
    ("minus",): "-",
    ("gedankenstrich",): "–",
    ("schrägstrich",): "/",
    # symbols
    ("prozentzeichen",): "%",
    ("paragraf",): "§",
    ("paragraph",): "§",
    ("sternchen",): "*",
    # line breaks
    ("zeilenumbruch",): "\n",
    ("neue", "zeile"): "\n",
    ("neuer", "absatz"): "\n\n",
    # round parentheses (+ synonyms)
    ("klammer", "auf"): "(",
    ("klammer", "zu"): ")",
    ("klammer", "öffnen"): "(",
    ("klammer", "schließen"): ")",
    ("runde", "klammer", "auf"): "(",
    ("runde", "klammer", "zu"): ")",
    # square / curly brackets
    ("eckige", "klammer", "auf"): "[",
    ("eckige", "klammer", "zu"): "]",
    ("geschweifte", "klammer", "auf"): "{",
    ("geschweifte", "klammer", "zu"): "}",
    # quotation marks (German „ … “) + synonyms
    ("anführungszeichen", "auf"): "„",
    ("anführungszeichen", "zu"): "“",
    ("anführungszeichen", "öffnen"): "„",
    ("anführungszeichen", "schließen"): "“",
    ("gänsefüßchen", "auf"): "„",
    ("gänsefüßchen", "zu"): "“",
}

_MAX_COMMAND_WORDS = 3

# per-mark (space_before, space_after) — words default to (True, True)
_SPACING: dict[str, tuple[bool, bool]] = {
    ",": (False, True),
    ".": (False, True),
    "?": (False, True),
    "!": (False, True),
    ":": (False, True),
    ";": (False, True),
    "…": (False, True),
    "%": (False, True),
    ")": (False, True),
    "]": (False, True),
    "}": (False, True),
    "“": (False, True),
    "(": (True, False),
    "[": (True, False),
    "{": (True, False),
    "„": (True, False),
    "-": (False, False),
    "/": (False, False),
    "–": (True, True),
    "§": (True, True),
    "*": (True, True),
    "\n": (False, False),
    "\n\n": (False, False),
}

# capitalization directives: affect the NEXT content word
_CASE_UPPER = {"großschreiben", "grossschreiben"}
_CASE_LOWER = {"kleinschreiben"}

_SENTENCE_ENDERS = ".!?\n"
_NUMBER = re.compile(r"\d+")

# Whisper attaches its own inferred sentence punctuation to words, especially
# around the pauses near a dictated command. In dictation mode all punctuation
# comes from the spoken commands, so that outer punctuation is stripped from
# every token — both to make commands match and to drop the now-stray marks.
# Internal characters (hyphen in "E-Mail", comma in "3,5") are kept because
# ``str.strip`` only removes leading/trailing chars.
_OUTER_PUNCT = ",.;:!?…\"„“”«»()"


class DictationCommands:
    """Convert spoken German punctuation words into marks."""

    def apply(self, text: str) -> str:
        for pattern, joined in _SPLIT_COMPOUNDS:
            text = pattern.sub(joined, text)
        cores = [token.strip(_OUTER_PUNCT) for token in text.split()]
        n = len(cores)

        atoms: list[tuple[str, bool, bool]] = []
        pending_case: str | None = None
        i = 0
        while i < n:
            core = cores[i]
            if not core:
                i += 1
                continue  # token was pure Whisper punctuation — drop it
            low = core.lower()

            if low in _CASE_UPPER:
                pending_case = "upper"
                i += 1
                continue
            if low in _CASE_LOWER:
                pending_case = "lower"
                i += 1
                continue

            # decimal comma: "3 Komma 5" -> "3,5" (attached, no surrounding space)
            if (
                low == "komma"
                and 0 < i < n - 1
                and _NUMBER.fullmatch(cores[i - 1])
                and _NUMBER.fullmatch(cores[i + 1])
            ):
                atoms.append((",", False, False))
                i += 1
                continue

            mark = self._match_command(cores, i, n)
            if mark is not None:
                length, symbol = mark
                atoms.append((symbol, *_SPACING[symbol]))
                i += length
                continue

            word = core
            if pending_case == "upper":
                word = word[:1].upper() + word[1:]
            elif pending_case == "lower":
                word = word[:1].lower() + word[1:]
            pending_case = None
            atoms.append((word, True, True))
            i += 1

        return self._recapitalize(self._join(atoms))

    @staticmethod
    def _match_command(cores: list[str], i: int, n: int) -> tuple[int, str] | None:
        for length in range(min(_MAX_COMMAND_WORDS, n - i), 0, -1):
            key = tuple(cores[j].lower() for j in range(i, i + length))
            symbol = _COMMANDS.get(key)
            if symbol is not None:
                return length, symbol
        return None

    @staticmethod
    def _join(atoms: list[tuple[str, bool, bool]]) -> str:
        out: list[str] = []
        prev_space_after = False
        for idx, (token, space_before, space_after) in enumerate(atoms):
            if idx > 0 and prev_space_after and space_before:
                out.append(" ")
            out.append(token)
            prev_space_after = space_after
        return "".join(out).strip()

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
