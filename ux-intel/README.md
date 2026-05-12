# ux-intel

Turn a narrated screen recording into structured, traceable UX feedback.

Drop in a video of someone narrating their way through your app. Out the
other end: a session directory of raw evidence, intermediate artifacts, a
human-readable review document, draft issues, and a "context cartridge"
designed for pasting into a coding agent.

See [`DESIGN.md`](DESIGN.md) for the architecture and design decisions.

## Install

Python 3.10+ and `ffmpeg` on `PATH`.

```bash
cd ux-intel
pip install -e .

export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...           # for Whisper transcription
```

## Quick start

```bash
ux-intel run path/to/walkthrough.mp4
```

This creates `sessions/<timestamp>-<id>/` and runs the full pipeline:

```
ingest → transcribe → frames → align → analyze → synthesize
```

When it finishes you'll see:

```
sessions/20260512-143027-a8b3f1/
  raw/                      # original input + extracted audio
  intermediates/            # transcript, frames, moments, observations
  outputs/
    review.md               # human-readable review
    issues.json             # draft issues
    clusters.json           # grouped themes
    context.md              # cartridge for coding agents
```

## Running stages individually

Useful when you want to iterate on the analyze prompt without paying for
transcription twice, or to swap in a different frame-extraction tuning.

```bash
ux-intel new path/to/walkthrough.mp4         # just creates the session
ux-intel ingest      sessions/<id>
ux-intel transcribe  sessions/<id>
ux-intel frames      sessions/<id> --sample-fps 1 --distance-threshold 8
ux-intel align       sessions/<id>
ux-intel analyze     sessions/<id> --effort high
ux-intel synthesize  sessions/<id> --effort high
ux-intel status      sessions/<id>
```

Each stage records its status in `session.json`. Re-running a stage overwrites
its artifact but leaves earlier stages untouched. A stage refuses to run if
its dependencies haven't completed.

## What each stage does

**ingest** — probes the video, extracts mono 16kHz audio. Writes
`video_metadata.json` and `raw/audio.wav`.

**transcribe** — sends audio to OpenAI Whisper with word-level timestamps.
Writes `transcript.json` and `transcript.txt`.

**frames** — samples the video at a low fixed rate, perceptual-hashes each
frame, keeps frames whose hash is far enough from the last kept frame (scene
change) or whose timestamp exceeds the interval floor (so static screens
still get periodic samples). Writes `frames.json` and `frames/frame-NNNN.jpg`.

**align** — groups transcript segments into "moments" using silence gaps,
topic-shift heuristics, and a max-duration ceiling. Each moment gets the
frame nearest to its midpoint. Writes `moments.json`.

**analyze** — one Claude call per moment. Sends the transcript text and the
primary frame to `claude-opus-4-7` with adaptive thinking and a JSON schema.
The system prompt is held byte-stable across all moments so prompt caching
amortizes the rubric. Writes `observations.json`.

**synthesize** — one Claude call ingests all observations and emits clusters,
draft issues, the review markdown, and the context cartridge. Streaming on
because outputs can be long. Writes `clusters.json`, `issues.json`,
`review.md`, `context.md`.

## Customizing

- **Different transcription provider**: implement the `Transcriber` protocol
  in `transcribe.py` and pass an instance to `transcribe_stage.run()`.
- **Frame extraction tuning**: `--sample-fps`, `--distance-threshold`,
  `--interval-floor` on the `frames` subcommand.
- **Moment grouping**: tweak `DEFAULT_MAX_MOMENT_S`, `RESTART_PHRASES`, and
  the silence gap in `align.py`.
- **Prompts**: `prompts.py` — both system prompts are isolated there.

## Evidence preservation

Every observation carries `moment_id`, `frame_ref`, `quote`, and timestamps.
Every cluster cites its observation IDs. Every issue cites its evidence.
Nothing in the final outputs is disconnected from the raw transcript and the
specific frame that supports it.

## Cost expectations

A 5-minute walkthrough typically produces 15–30 moments. With prompt caching
the per-moment Claude call is dominated by the image (~1500 tokens) and the
fresh transcript snippet. Rough order-of-magnitude:

| Stage        | Cost     | Notes                                       |
|--------------|----------|---------------------------------------------|
| transcribe   | ~$0.03   | OpenAI Whisper at $0.006/min                |
| analyze      | ~$0.30   | 20 moments × ~$0.015 (Opus 4.7, cached)     |
| synthesize   | ~$0.30   | one call, larger output                     |

These will vary with effort level, narration density, and resolution.

## Limitations (MVP)

- Single narrator assumed. No diarization.
- English-tuned rubric. Whisper supports more languages but the prompts are
  English.
- Heuristic frame extraction — works well on screen-recording footage with
  natural transitions; less reliable on scrolling-heavy content.
- No GitHub/Linear integration. Issues are drafts in `issues.json`.
- No web UI. The artifact directory is the surface.

The architecture leaves clean room for each of these to grow — see the
"Future expansion" section of [`DESIGN.md`](DESIGN.md).
