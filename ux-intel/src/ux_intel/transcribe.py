"""Stage 2: transcribe.

OpenAI Whisper API with word-level timestamps. The integration is wrapped in a
Transcriber protocol so a local-whisper or Deepgram adapter can drop in later
without touching the rest of the pipeline.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from openai import OpenAI

from .schemas import Transcript, TranscriptSegment, TranscriptWord
from .session import STAGE_TRANSCRIBE, Session


class Transcriber(Protocol):
    def transcribe(self, audio_path: Path) -> Transcript: ...


class OpenAIWhisperTranscriber:
    """`whisper-1` via the OpenAI API.

    Word-level timestamps are requested so the aligner can split moments on
    silence gaps with sub-second precision.
    """

    def __init__(self, model: str = "whisper-1", api_key: str | None = None):
        self.model = model
        self.client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))

    def transcribe(self, audio_path: Path) -> Transcript:
        with audio_path.open("rb") as f:
            response = self.client.audio.transcriptions.create(
                file=f,
                model=self.model,
                response_format="verbose_json",
                timestamp_granularities=["segment", "word"],
            )
        return _parse_whisper_response(response)


def run(session: Session, transcriber: Transcriber | None = None) -> Transcript:
    session.require_dependencies(STAGE_TRANSCRIBE)
    session.mark_running(STAGE_TRANSCRIBE)
    try:
        transcriber = transcriber or OpenAIWhisperTranscriber()
        transcript = transcriber.transcribe(session.audio_path)
        session.transcript_path.write_text(transcript.model_dump_json(indent=2))
        session.transcript_text_path.write_text(transcript.full_text)
        session.mark_completed(
            STAGE_TRANSCRIBE,
            notes=f"{len(transcript.segments)} segments, lang={transcript.language}",
        )
        return transcript
    except Exception as exc:
        session.mark_failed(STAGE_TRANSCRIBE, str(exc))
        raise


def _parse_whisper_response(response) -> Transcript:
    raw = response.model_dump() if hasattr(response, "model_dump") else dict(response)
    raw_segments = raw.get("segments") or []
    raw_words = raw.get("words") or []

    words_by_segment: dict[int, list[TranscriptWord]] = {}
    if raw_words and raw_segments:
        # Whisper returns a flat word list; attach each word to the segment
        # whose [start, end] contains its midpoint.
        for w in raw_words:
            midpoint = (float(w["start"]) + float(w["end"])) / 2
            for i, seg in enumerate(raw_segments):
                if float(seg["start"]) <= midpoint <= float(seg["end"]):
                    words_by_segment.setdefault(i, []).append(
                        TranscriptWord(word=w["word"], start=float(w["start"]), end=float(w["end"]))
                    )
                    break

    segments = [
        TranscriptSegment(
            id=i,
            start=float(seg["start"]),
            end=float(seg["end"]),
            text=seg["text"].strip(),
            words=words_by_segment.get(i, []),
        )
        for i, seg in enumerate(raw_segments)
    ]

    return Transcript(
        language=raw.get("language", "en"),
        duration_s=float(raw.get("duration", segments[-1].end if segments else 0.0)),
        segments=segments,
        full_text=raw.get("text", " ".join(s.text for s in segments)),
    )
