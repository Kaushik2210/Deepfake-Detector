# VeriFrame Inference Service

FastAPI service running the detection pipeline. As of Phase 4 it handles both **images and short video clips**.

## What runs today

| Piece | Status |
|---|---|
| Face detection (YuNet) | ✅ |
| Stream A — ViT classifier with test-time augmentation | ✅ |
| Stream B — frequency and signal forensics | ✅ |
| Stream C — temporal/biological signals (video only) | ✅ evidence only, no fusion weight yet — see below |
| Stream D — provenance (C2PA, EXIF, generator metadata) | ✅ |
| Weighted fusion with provenance override | ✅ |
| Calibration (temperature scaling) fitted by the eval harness | ✅ |
| Evaluation harness with cross-dataset protocol | ✅ images only |
| Per-face / per-frame results, face map, plain-language conclusion | ✅ |
| Grad-CAM heatmap artifacts | ✅ |
| Envelope checks + confidence penalty | ✅ |
| Perceptual hash | ✅ |
| ONNX export + inference path | ✅ |
| Video upload: sparse + dense frame sampling, per-frame timeline | ✅ |
| `POST /v1/analyze`, `GET /v1/analyze/{job_id}`, `GET /v1/health` | ✅ |
| Second ensemble backbone | ⚠️ machinery built, no suitable model — see `LICENSES.md` |
| Lip-sync / audio-visual desync | ⚠️ not implemented, licence-blocked — see `LICENSES.md` |
| Audio pipeline, `POST /v1/analyze/hash` | ❌ later phases |

## Setup

Python 3.11 is required (pinned by the project spec).

```bash
conda create -n veriframe python=3.11 -y
```

Install PyTorch first from the CPU index, then the rest:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

```bash
pip install -e ".[dev]"
```

Pre-download model weights so the first request isn't slow:

```bash
python scripts/fetch_models.py
```

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

```bash
curl -F "file=@face.jpg;type=image/jpeg" http://localhost:8000/v1/analyze
```

```bash
curl -F "file=@clip.mp4;type=video/mp4" http://localhost:8000/v1/analyze
```

## Tests

The suite is split so CI needs no model weights and no network. Tests marked `model` download ~340 MB of weights on first run.

```bash
pytest -m "not model"
```

```bash
pytest
```

## How a score is produced

1. **Decode** the upload, reject anything OpenCV can't read.
2. **Detect faces** with YuNet. No face means no evidence — see below.
3. **Score each face** with the ViT over 4 test-time augmentations (2 scales × horizontal flip), averaging *logits* before softmax.
4. **Aggregate** across faces by taking the maximum, since one manipulated face in an otherwise genuine image still makes the image manipulated. Per-face scores are always reported alongside so the aggregate isn't hiding them.
5. **Assess the envelope** — face size, resolution, blur, illumination, JPEG quality — and accumulate a multiplicative confidence penalty with a human-readable reason for each.
6. **Apply the penalty** by shrinking the score toward 0.5 and widening the uncertainty interval. A score we can't stand behind moves toward "inconclusive" rather than staying confident.
7. **Generate a Grad-CAM heatmap** for the face that drove the aggregate.

### Deliberate behaviours worth knowing

**No face detected returns 0.5 / "Mixed signals", not a low score.** A low score would claim we looked and found nothing. We didn't look, because there was nothing to look at. The envelope carries an explicit penalty saying so.

**Every score is penalised as uncalibrated.** Raw softmax outputs are overconfident. Temperature scaling is fitted in Phase 3 from the eval harness; until then a permanent penalty and a stated reason ride along with every report.

**Uncertainty comes from test-time-augmentation spread, which is a weak proxy.** The architecture calls for ensemble disagreement across architecturally different backbones. Phase 1 has one backbone, so TTA spread substitutes — it measures sensitivity to flip and scale, not error decorrelation. In practice this spread is very small (~0.001 on clean inputs), which is exactly why it is labelled as weak everywhere it surfaces and replaced in Phase 3.

**Accuracy numbers are not quoted anywhere.** The upstream model reports 92.12% in-dataset accuracy with no cross-dataset protocol. Under principle 5 that number is not defensible as a product claim, so it appears only in `LICENSES.md` as provenance, never in the API or UI.

## How a video score is produced

Video reuses the image pipeline's face detection, spatial classifier, frequency stream, and provenance stream — applied per sampled frame instead of once — plus a new Stream C. Two different frame samples are taken, because the two halves of the pipeline need different things:

1. **Sparse sample (≤24 frames).** Uniform time buckets, with a scene-change-biased pick within each bucket, so a static clip is sampled evenly and a clip with a cut or sudden change is more likely to catch it. Each sampled frame's largest face runs through Streams A and B exactly as an image would. Only the top-3 highest-scoring frames get a Grad-CAM heatmap — generating one per frame at up to 24 frames would risk the runtime this cap exists to protect — but every sampled frame's score appears in the timeline regardless.
2. **Dense window (≤300 frames, ≤12s, up to 25 fps).** A contiguous, evenly-spaced window centred in the clip, decode-and-landmark-only (no classifier), feeding Stream C. rPPG needs to resolve a 0.7-4 Hz signal, which by the Nyquist criterion needs roughly 8 Hz sampling — the sparse sample, at best ~1 fps over a full clip, is nowhere close.

Multi-person clips are not tracked per-person over time: only the largest detected face in each sampled frame is analysed, so in a clip with several people the "primary subject" can differ from frame to frame. Documented as a limitation, not fixed — proper multi-identity tracking across a clip is a larger feature than this phase scopes.

### Stream C (temporal/biological)

Four sub-signals, all unsupervised heuristics with hand-derived thresholds, matching Stream B's own caveat:

- **Optical flow discontinuity** — Farneback flow magnitude at the face-hull boundary vs. its interior. A face-swap blending seam tends to move slightly differently from what it's composited onto; ordinary motion blur or a fast head turn produces the same pattern, so this is one weak vote, not a detector.
- **Blink analysis** — from MediaPipe's `eyeBlinkLeft`/`eyeBlinkRight` blendshapes (a trained regression), not a hand-rolled eye-aspect-ratio heuristic. Absent blinking was a documented weakness of early GAN synthesis; modern generators reproduce it, and real people blink less while concentrating on camera, so this is a weak, dated signal.
- **Head-pose jitter** — frame-to-frame angular velocity from MediaPipe's own fitted transformation matrix (no separate solvePnP fit). Physically implausible pose instability nudges the score; genuine fast head motion looks the same.
- **rPPG** — a CHROM-algorithm pulse signal from forehead/cheek skin regions, bandpass-filtered to 0.7-4 Hz. A coherent, physiologically plausible pulse is mildly reassuring (uncommon by chance); no coherent pulse is the *common* case even on real footage — compression and lighting destroy it easily — so absence carries almost no weight.
- **Lip-sync is not implemented.** Wav2Lip's weights are non-commercial (BBC-licensed LRS2 training data); SyncNet's weights have no stated licence. See `LICENSES.md`.

Stream C's score is reported as evidence but **does not move the fused result**: no video-labelled dataset exists yet to derive a fusion weight from, so it carries weight 0.0, the same treatment Stream B had before Phase 3 measured it.

## Known limitation observed in Phase 1

On a genuine 1980s photograph (`grace_hopper.jpg`, US Navy, public domain) the classifier returns a raw score of **0.712**, reported as 0.68 / "Mixed signals" after the calibration penalty. That is a false positive on real, unmanipulated media, and it is the distribution-shift failure the project's principles exist to handle: the model was trained on modern face imagery and a scanned film photograph sits well outside that. The system's response — a "Mixed signals / manual review advised" band rather than a confident accusation — is the designed behaviour, but this is concrete evidence for why binary verdicts are prohibited and why the Phase 3 cross-dataset eval harness must precede any accuracy claim.

## Configuration

Environment variables, all prefixed `VERIFRAME_` (see `app/config.py`):

| Variable | Default | Purpose |
|---|---|---|
| `VERIFRAME_SPATIAL_MODEL_ID` | `prithivMLmods/Deep-Fake-Detector-v2-Model` | Stream A checkpoint |
| `VERIFRAME_SPATIAL_MODEL_REVISION` | `main` | Resolved to a commit SHA and reported in `model_versions` |
| `VERIFRAME_MIN_FACE_PX` | `64` | Below this, a face-size penalty applies |
| `VERIFRAME_MIN_JPEG_QUALITY` | `70` | Below this, a compression penalty applies |
| `VERIFRAME_MEDIA_TTL_HOURS` | `24` | Report retention |
| `VERIFRAME_PUBLIC_BASE_URL` | `http://localhost:8000` | Base for artifact URLs |
| `VERIFRAME_BANDS_JSON` | *(auto-located)* | Override path to the canonical band table |
| `VERIFRAME_MAX_VIDEO_BYTES` | `100 MB` | Video upload size limit |
| `VERIFRAME_MAX_VIDEO_DURATION_SECONDS` | `60` | Video duration limit; longer clips are rejected (HTTP 422) |
| `VERIFRAME_VIDEO_SPARSE_FRAME_CAP` | `24` | Frames analysed by Streams A/B per video |
| `VERIFRAME_VIDEO_SPARSE_HEATMAP_TOP_K` | `3` | How many sampled frames get a Grad-CAM heatmap |
| `VERIFRAME_VIDEO_DENSE_WINDOW_MAX_SECONDS` | `12` | Stream C's dense-window length |
| `VERIFRAME_VIDEO_DENSE_WINDOW_TARGET_FPS` | `25` | Stream C's dense-window sampling rate |
