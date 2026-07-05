"""Accessible Word (.docx) exporter.

Accessibility requirements (project brief, "Exported documents must
themselves be accessible"):

* Real Word *styles* — ``Heading 1`` / ``Heading 2`` / body paragraphs — so
  screen-reader users can navigate the document by heading in Word. No
  visual-only bold/font-size tricks.
* The document language is set to ``de-DE`` (default paragraph style and core
  properties) so screen readers pick the correct speech synthesizer voice.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt

from engine.types import TranscriptResult

_LANG = "de-DE"


def _set_document_language(document: object) -> None:
    """Set de-DE on the Normal style so every paragraph inherits it."""
    style = document.styles["Normal"]  # type: ignore[attr-defined]
    rpr = style.element.get_or_add_rPr()
    lang = rpr.find(qn("w:lang"))
    if lang is None:
        lang = rpr.makeelement(qn("w:lang"), {})
        rpr.append(lang)
    lang.set(qn("w:val"), _LANG)


def _format_duration(seconds: float) -> str:
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def to_docx(result: TranscriptResult) -> bytes:
    document = Document()
    _set_document_language(document)
    core = document.core_properties
    core.language = _LANG
    core.title = "Transkript"

    document.add_heading("Transkript", level=1)

    meta = document.add_paragraph()
    meta.add_run(
        "Erstellt: "
        f"{datetime.now(timezone.utc).astimezone().strftime('%d.%m.%Y %H:%M')}\n"
        f"Dauer der Aufnahme: {_format_duration(result.info.duration)}\n"
        f"Sprache: Deutsch ({result.info.language})\n"
        f"Modell: {result.info.model}"
    ).font.size = Pt(10)

    document.add_heading("Inhalt", level=2)

    if result.has_speakers:
        current_speaker: str | None = None
        for seg in result.segments:
            text = seg.text.strip()
            if not text:
                continue
            speaker = seg.speaker or "Unbekannt"
            if speaker != current_speaker:
                document.add_heading(speaker, level=3)
                current_speaker = speaker
            document.add_paragraph(text)
    else:
        for seg in result.segments:
            text = seg.text.strip()
            if text:
                document.add_paragraph(text)

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
