# example-session

A synthetic session showing the artifact shape the pipeline produces.

This is not the output of a real run — the JSON files were hand-written to
document the schema concretely. The video file and frame images are omitted.

See `../../DESIGN.md` for the architecture this session illustrates.

Files:

- `session.json` — per-stage status and metadata
- `intermediates/video_metadata.json` — ingest output
- `intermediates/transcript.json` — transcribe output (truncated)
- `intermediates/frames.json` — frames output
- `intermediates/moments.json` — align output
- `intermediates/observations.json` — analyze output
- `outputs/clusters.json` — synthesize output
- `outputs/issues.json` — synthesize output
- `outputs/review.md` — synthesize output
- `outputs/context.md` — synthesize output
