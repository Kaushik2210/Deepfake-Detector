# VeriFrame Inference Service

FastAPI service running the detection pipeline. Phase 1 covers **images only**, via Stream A (spatial classifier).

## What runs today

| Piece | Status |
|---|---|
| Face detection (YuNet) | ✅ |
| Stream A — ViT classifier with test-time augmentation | ✅ |
| Stream B — frequency and signal forensics | ✅ |
| Stream D — provenance (C2PA, EXIF, generator metadata) | ✅ |
| Weighted fusion with provenance override | ✅ |
| Calibration (temperature scaling) fitted by the eval harness | ✅ |
| Evaluation harness with cross-dataset protocol | ✅ |
| Per-face results, face map, plain-language conclusion | ✅ |
| Grad-CAM heatmap artifacts | ✅ |
| Envelope checks + confidence penalty | ✅ |
| Perceptual hash | ✅ |
| ONNX export + inference path | ✅ |
| `POST /v1/analyze`, `GET /v1/analyze/{job_id}`, `GET /v1/health` | ✅ |
| Second ensemble backbone | ⚠️ machinery built, no suitable model — see `LICENSES.md` |
| Stream C, video, audio, `POST /v1/analyze/hash` | ❌ later phases |

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
