# UX Intelligence Pipeline — Design

## What this is

A pipeline that turns a narrated screen recording of someone using an app into
structured, traceable, implementation-ready feedback.

Input: a video file with synchronized narration.
Output: a session directory with raw evidence, intermediate artifacts, and
review documents that downstream humans or coding agents can act on.

The system preserves the chain from spoken word → screen state → interpreted
observation → grouped theme → drafted issue, so any claim in the final review
can be traced back to a timestamp, a transcript line, and a frame.

## Goals (MVP)

1. Ingest a single video file and extract synchronized transcript + visual states.
2. Produce structured observations from loosely narrated feedback.
3. Group recurring themes; preserve uncertainty where interpretation is weak.
4. Emit both machine-readable JSON and human-readable Markdown.
5. Be inspectable and resumable at every stage.

Non-goals (for now): real-time analysis, multi-speaker diarization, direct
GitHub/Linear integration, browser-based recording UI, multi-language support.

## Architecture

A stage-based pipeline. Each stage reads the session directory, writes its
artifact, and updates session state. Any stage can be re-run without re-running
the earlier ones — useful for iterating on the LLM prompt without paying for
transcription twice.

```
        video.mp4
            │
   ┌────────▼─────────┐
   │  1. ingest       │  probe metadata, extract mono 16k audio
   └────────┬─────────┘
            │
   ┌────────▼─────────┐
   │  2. transcribe   │  Whisper → word/segment-level timestamps
   └────────┬─────────┘
            │
   ┌────────▼─────────┐
   │  3. frames       │  ffmpeg + scene-change scoring → keyframes
   └────────┬─────────┘
            │
   ┌────────▼─────────┐
   │  4. align        │  group transcript into "moments", attach nearest frame
   └────────┬─────────┘
            │
   ┌────────▼─────────┐
   │  5. analyze      │  Claude multimodal: text + frame → structured observation
   └────────┬─────────┘     (prompt cached system prompt, JSON-schema output)
            │
   ┌────────▼─────────┐
   │  6. synthesize   │  cluster, generate review.md, issues.json, context cartridge
   └────────┬─────────┘
            │
       outputs/
```

### Session layout

```
sessions/<session-id>/
  session.json                # metadata + per-stage status + schema versions
  raw/
    walkthrough.mp4           # symlink or copy of the original input
    audio.wav                 # extracted mono 16k audio
  intermediates/
    transcript.json           # full Whisper response with timestamps
    transcript.txt            # plain text (debug / grep-friendly)
    frames.json               # frame metadata (timestamp, hash, scene score)
    frames/frame-NNNN.jpg     # one image per keyframe
    moments.json              # transcript segments aligned to frames
    observations.json         # per-moment structured observations
  outputs/
    review.md                 # human-readable review
    issues.json               # draft issue candidates
    clusters.json             # grouped themes
    context.md                # implementation-oriented cartridge for AI agents
```

### Stage independence

Each stage records its `schema_version` and `completed_at` in `session.json`.
Re-running a stage overwrites its artifact but leaves earlier stages untouched.
A stage that depends on a prior artifact checks schema compatibility before
running and refuses to proceed on a mismatch — failures are surfaced, not
silently papered over.

## Key design decisions and tradeoffs

### Visual state extraction

Fixed-interval screenshots miss meaningful transitions and over-sample static
screens. Instead the pipeline scores adjacent frames using ffmpeg's `select`
filter with `scene` metadata, keeps frames above a configurable threshold, and
also keeps one frame per N seconds as a floor. Frames are hashed
(perceptual hash) and near-duplicates are dropped.

This is heuristic — not a vision model. It works because narrated walkthroughs
have natural scene boundaries (navigation, modals, scrolls). When it doesn't,
the analyze stage tolerates it: the multimodal call sees whatever frame is
nearest in time to the spoken moment, and Claude is good at reading screens
even when they aren't optimally chosen.

### Moment construction

A "moment" is the unit of analysis: roughly one coherent thought from the
narrator. The aligner groups transcript segments using two signals:

- Silence gaps (Whisper's segment boundaries already pause on these).
- Topic shifts (heuristically, by looking for restart phrases like "okay so",
  "now I'm going to", "next thing").

Each moment gets the frame whose timestamp is closest to the moment's midpoint.
Adjacent moments may share a frame; that's fine.

### LLM analysis

One Claude call per moment. The system prompt is large (extraction rubric,
schema, examples) and identical across all moments in a session, so prompt
caching dominates the cost — the first moment pays the write, every subsequent
moment reads.

The response is constrained to a JSON schema via `output_config.format`. The
schema includes explicit `confidence` and `interpretation_basis` fields so the
model has a place to express uncertainty rather than hallucinating precision.

The frame is passed inline as an image content block. Claude reads the screen
directly — no separate OCR pass.

Model: `claude-opus-4-7` with adaptive thinking and `effort: high`. This is a
quality-sensitive task; cheaper models miss subtleties in narration.

### Synthesis and clustering

For MVP, a single Claude call ingests all observations and produces:

- Cluster assignments (which observations are talking about the same underlying
  issue).
- A markdown review document grouped by cluster, with citations back to
  moments.
- Draft issue candidates in a structured shape that maps cleanly to GitHub or
  Linear.
- A "context cartridge" — a markdown digest tuned for being pasted into
  another AI coding agent's context window. Heavy on file/component references,
  light on prose.

This avoids an embedding store dependency for MVP. A future pass can replace
the LLM clustering with embedding-based clustering once observation volume
warrants it.

### Evidence preservation

Every observation carries:

- `moment_id` — back-references to `moments.json`
- `frame_ref` — path to the screenshot
- `quote` — the verbatim transcript excerpt
- `t_start` / `t_end` — original video timestamps

Every cluster carries the list of observation IDs that compose it. Every issue
draft cites the cluster it came from. Nothing in the final outputs is
disconnected from raw evidence.

## What the system does *not* do (and why)

- **No real-time analysis.** Batch processing is simpler, cheaper, and
  sufficient for the "review my prototype" use case. Streaming pipelines have a
  much higher implementation cost for a marginal UX improvement.
- **No speaker diarization.** Assumes a single narrator.
- **No direct GitHub/Linear/Jira API integration.** The outputs are drafts a
  human reviews before filing. Auto-filing review-quality bugs is a separate
  problem.
- **No web UI.** A CLI that produces a directory tree is the simplest possible
  surface and composes well with everything else (editors, agents, version
  control).
- **No client-side OCR or DOM extraction.** Multimodal Claude handles screens
  competently. The architecture leaves room to add these as additional inputs
  later (an `accessibility_tree.json` per moment, for example).

## Future expansion

Clean places the architecture can grow into:

- **Richer inputs.** Click/touch event logs, DOM snapshots, accessibility
  trees, network HAR files all slot in as additional per-moment context for
  the analyze stage.
- **Embedding-based clustering.** Replace or augment the LLM clustering pass
  for sessions with hundreds of observations.
- **Cross-session intelligence.** A second tier that ingests multiple session
  outputs and detects patterns across users, builds.
- **Active review loops.** A reviewer corrects an observation; the correction
  feeds back into the rubric (few-shot examples in the system prompt).
- **Auto-filed drafts.** Once issue drafts are reliably high-quality, push
  them as draft PRs / issues with human approval gates.
- **Live narration.** Streaming pipeline that ingests audio + screen capture
  in real time and surfaces observations as they happen — significant
  re-architecture but the per-moment unit is the same.

## Assumptions

- The user can run Python 3.10+ locally and has ffmpeg installed.
- The narrator speaks English. (Whisper supports more, but the rubric is
  English-tuned.)
- One narrator per video.
- The video has audio. (Silent walkthroughs need a different pipeline.)
- The user has API credentials for both Anthropic and OpenAI (for Whisper).
  An adapter for local Whisper is a small follow-up and the interface is
  already abstracted.
