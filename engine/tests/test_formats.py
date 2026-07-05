from __future__ import annotations

import json
from io import BytesIO

from docx import Document

from engine.formats import render, write_outputs
from engine.formats.docxfmt import to_docx
from engine.formats.jsonfmt import to_json
from engine.formats.subtitles import to_srt, to_vtt
from engine.formats.text import to_txt
from engine.types import OutputFormat, Segment, TranscriptResult


class TestTxt:
    def test_one_line_per_segment(self, sample_result: TranscriptResult) -> None:
        assert to_txt(sample_result) == (
            "Guten Tag, Frau Müller.\nDie Prüfung findet am fünften Juli statt.\n"
        )

    def test_speaker_labels(self, sample_result: TranscriptResult) -> None:
        sample_result.segments[0].speaker = "Sprecher 1"
        assert to_txt(sample_result).startswith("Sprecher 1: Guten Tag")

    def test_empty_transcript(self, sample_result: TranscriptResult) -> None:
        empty = TranscriptResult(segments=[], info=sample_result.info)
        assert to_txt(empty) == ""


class TestSrt:
    def test_structure(self, sample_result: TranscriptResult) -> None:
        srt = to_srt(sample_result)
        blocks = srt.strip().split("\n\n")
        assert len(blocks) == 2
        assert blocks[0].splitlines() == [
            "1",
            "00:00:00,000 --> 00:00:02,500",
            "Guten Tag, Frau Müller.",
        ]
        assert blocks[1].startswith("2\n00:00:03,000 --> 00:00:06,000")

    def test_blank_segments_skipped_and_index_stays_sequential(
        self, sample_result: TranscriptResult
    ) -> None:
        sample_result.segments.insert(
            1, Segment(id=99, start=2.5, end=3.0, text="   ")
        )
        srt = to_srt(sample_result)
        assert "\n\n2\n" in srt  # second real cue is numbered 2, not 3
        assert srt.count("-->") == 2


class TestVtt:
    def test_structure(self, sample_result: TranscriptResult) -> None:
        vtt = to_vtt(sample_result)
        lines = vtt.splitlines()
        assert lines[0] == "WEBVTT"
        assert "00:00:00.000 --> 00:00:02.500" in lines
        assert "Guten Tag, Frau Müller." in lines


class TestJson:
    def test_word_level_timestamps(self, sample_result: TranscriptResult) -> None:
        payload = json.loads(to_json(sample_result))
        assert payload["schema_version"] == 1
        assert payload["info"]["language"] == "de"
        first_word = payload["segments"][0]["words"][0]
        assert first_word == {"start": 0.0, "end": 0.4, "text": "Guten", "probability": 0.99}

    def test_umlauts_not_escaped(self, sample_result: TranscriptResult) -> None:
        assert "Müller" in to_json(sample_result)


class TestDocx:
    def test_headings_use_real_styles(self, sample_result: TranscriptResult) -> None:
        document = Document(BytesIO(to_docx(sample_result)))
        styles = [(p.style.name, p.text) for p in document.paragraphs]
        assert ("Heading 1", "Transkript") in styles
        assert ("Heading 2", "Inhalt") in styles
        body = [text for style, text in styles if style == "Normal" and text]
        assert "Guten Tag, Frau Müller." in body

    def test_document_language_is_german(self, sample_result: TranscriptResult) -> None:
        document = Document(BytesIO(to_docx(sample_result)))
        assert document.core_properties.language == "de-DE"
        rpr = document.styles["Normal"].element.get_or_add_rPr()
        lang = rpr.find(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}lang"
        )
        assert lang is not None
        assert lang.get(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val"
        ) == "de-DE"

    def test_speaker_turns_become_headings(self, sample_result: TranscriptResult) -> None:
        sample_result.segments[0].speaker = "Sprecher 1"
        sample_result.segments[1].speaker = "Sprecher 2"
        document = Document(BytesIO(to_docx(sample_result)))
        h3 = [p.text for p in document.paragraphs if p.style.name == "Heading 3"]
        assert h3 == ["Sprecher 1", "Sprecher 2"]


class TestWriteOutputs:
    def test_writes_all_formats(self, sample_result: TranscriptResult, tmp_path) -> None:
        written = write_outputs(
            sample_result, list(OutputFormat), tmp_path, "meeting"
        )
        assert {p.name for p in written} == {
            "meeting.txt",
            "meeting.srt",
            "meeting.vtt",
            "meeting.json",
            "meeting.docx",
        }
        for path in written:
            assert path.stat().st_size > 0

    def test_render_matches_exporters(self, sample_result: TranscriptResult) -> None:
        assert render(sample_result, OutputFormat.TXT).decode("utf-8") == to_txt(sample_result)
