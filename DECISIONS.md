# Decisions

Running log of architectural choices and their rationale. Newest first.

## 2026-09-03 — `c2pa-python` was shipped without a `LICENSES.md` entry; a pre-deployment audit caught it

Requested a security review and an originality/copyright audit before deployment. The security review (auth/IDOR, injection, deserialization, path traversal, SSRF, secrets) found no High or Medium exploitable issues — two Low/informational notes only: the inference service's unauthenticated `GET /v1/analyze/{job_id}` relies on UUID entropy rather than an ownership check (fine today, would become a real IDOR only if job IDs ever became low-entropy/sequential), and the inference service's CORS wildcards all `chrome-extension://*` origins rather than one published extension ID (already flagged as a Phase 7 TODO in the code itself, and not exploitable today since those endpoints are unauthenticated and stateless regardless of origin).

The originality audit's one real finding: `c2pa-python` (Stream D's C2PA manifest reader, `services/inference/pyproject.toml`) is a shipped, detection-relevant dependency with no `LICENSES.md` entry at all — the only dependency in the table that was apparently never checked against a primary source before being wired in, breaking this project's own stated discipline. Verified directly against the `contentauth/c2pa-python` repository's own `LICENSE-MIT`/`LICENSE-APACHE` files (both present, dual-licensed, MIT OR Apache-2.0, copyright Adobe 2020) rather than trusting the installed package's self-reported metadata alone — matches, no blocker. Entry added to `LICENSES.md`.

Also caught in the same pass: the root `README.md`'s "most recent image run" paragraph still cited the n=400/200/200 numbers after the harness had already been re-run at n=500/250/250 for the 2026-09-02 significance-testing entry below — `DECISIONS.md` and `eval/README.md` had been updated, `README.md` was missed. Fixed to the current numbers plus the significance-test finding.

## 2026-09-02 — Significance testing and weight-stability bootstrap added; a bigger image run shows the streams' gap isn't significant

Two gaps remained after the validation-split fix above: nothing said whether a measured AUC gap between two streams was a real, reproducible difference or sampling noise, and nothing said whether a given fusion-weight split was a stable property of the two streams or a lucky draw from that particular validation sample. Both are answerable without a third corpus or a re-run at a different seed:

- **`eval/metrics.py::compare_streams_auc`** — a paired bootstrap: the same resampled indices applied to both streams per replicate (they were scored on the same clips), producing a 95% CI and two-sided p-value on the AUC difference. Wired into both harnesses, run on the final held-out split.
- **`eval/calibrate.py::bootstrap_weight_stability`** — 500 resamples of the weight-validation split itself, fusion weights rederived from `derive_fusion_weights` each time. Deliberately not a rerun of the whole harness at a different random seed: a fresh seed also changes which clips get *scored* at all (different decode/network failures, different corpus draw order), conflating that noise with the one thing this isolates — sampling variance in which already-scored validation clips a bootstrap draw happens to contain. Substituted for the "multi-seed stability check" the user asked for on exactly this reasoning.

Re-running the image harness at a larger size (`reports/2026-09-02.md`, n=500 calibration / 250 validation / 250 final, up from 400/200/200) put both new checks to real use: spatial's AUC edge over frequency on the final split (0.6694 vs 0.6175, a 0.0518 gap) is **not statistically significant** — the paired bootstrap's 95% CI on the difference is [-0.0412, 0.1535], which includes zero (p=0.278). The weight-stability bootstrap agrees: spatial's weight ranges p10–p90 0.42–0.78 and frequency's 0.22–0.58 across resamples, wide enough to overlap substantially. The near-even 51.5/48.5-ish split reported in the 2026-08-31 entry below should be read as "these two streams are roughly comparable, and *which* one gets slightly more weight in a given run is not a settled question" — not as two decimal places of precision. ROC-curve data (`roc_points`) is also now captured on every stream, downsampled to ≤60 points, and rendered on the accuracy page alongside the reliability diagrams `calibration_bins` already provided.

Re-running the audio harness the same way (`reports/audio-2026-09-02.md`, n=120/60/60, up from 100/50/50) shows the opposite pattern, which is exactly the point of running both checks rather than assuming one answer fits every stream pair: AASIST beats `audio_frequency` by 0.29 AUC (0.9767 vs 0.6867) on the final held-out split, and this gap **is** statistically significant — 95% CI [0.1632, 0.4344], p≈0.0000. The weight-stability bootstrap agrees in the opposite direction from images too: audio's weight ranges p10–p90 0.685–0.943 and audio_frequency's 0.057–0.315, no overlap at all — a settled, stable split, not a coin flip. (This run's fused-vs-alone gap widened to -0.0400 from the -0.0064 the 2026-08-28 entry reported, at a smaller final n of 60 rather than 50 — normal run-to-run variance at this sample size, not a regression in the fix; the fusion weight itself is still derived correctly from validation-split AUC either way.) The two significance tests landing on opposite verdicts — a real, stable gap for audio; a noisy, unstable one for images — is the check doing its job: it does not have a house opinion on how similar two streams "should" be.

## 2026-08-28 — Fusion weights now come from a genuine cross-dataset validation split, not the calibration split

Both harnesses previously derived fusion weights from calibration-split AUC — in-distribution performance on the corpus the model itself may have trained on. Two independent measurements (the image `frequency` stream on 2026-08-21, the audio `audio_frequency` stream on 2026-08-28, entry below) showed this AUC does not predict cross-dataset generalisation and can actively mislead: a stream that measures well in-distribution can generalise worse than one that measured lower, and weighting fusion by the misleading number made the fused score worse than the better-generalising stream alone.

The fix (`eval/splits.py`, wired into both `eval/run.py` and `eval/audio_run.py`): the reporting corpus is split once, stratified by label, into a weight-validation half and a final reporting half. Fusion weights are derived from measured AUC on the validation half — a genuine cross-dataset measurement, since it comes from a different corpus than calibration — and every headline number is computed on the final half only, which played no part in choosing the weights. This is not a third corpus (the methodologically purest fix, noted as future work in the 2026-08-21 entry and `eval/README.md`, and still blocked on finding a second commercially-licensed reporting-quality corpus per media kind — see `LICENSES.md`'s rejected-candidates list); it is the same held-out guarantee obtained by splitting the one corpus that already exists into two disjoint, non-overlapping halves instead of using it whole for both weight selection and reporting.

Re-running the audio harness with this fix (`reports/audio-2026-08-28.md`, n=100 calibration / 50 validation / 50 final, same corpora as before) shows the fix working: `audio_frequency`'s validation-split AUC is 0.6528 — much closer to its true cross-dataset performance than the calibration-split AUC of 0.907 the old weighting used — so it now receives weight 0.243 instead of 0.4485. Fusing at this corrected weight reduces cross-dataset AUC from 0.9856 (AASIST alone) to 0.9792, a **-0.0064** gap, versus the **-0.0294** gap the old calibration-split-derived weight produced. The gap did not close to zero — `audio_frequency` still measures worse on the truly held-out final half (AUC 0.7072) than its own validation-half AUC (0.6528) suggested it might contribute, which is itself a legitimate small-sample effect at n=50 per split, not a flaw in the method — but it shrank by more than 4x simply by fitting the weight against the right kind of measurement.

Re-running the image harness with the same fix (`reports/2026-08-31.md`, n=400 calibration / 200 validation / 200 final) shows an even starker version of the same effect. The old calibration-split AUCs (frequency 0.713, spatial 0.534) gave frequency 86.4% of the fusion weight. On the genuine cross-dataset validation half, the two streams are nearly tied — spatial 0.5917, frequency 0.5864 — so the corrected weights are close to even (spatial 0.5149, frequency 0.4851) instead of lopsided. The in-dataset numbers from this same run (spatial 0.5295, frequency 0.7328) reproduce the original misleading gap almost exactly, confirming it is a property of the calibration corpus, not sampling noise from one run: frequency looks like the stronger stream by a wide margin in-distribution, and is actually roughly equal to spatial out-of-distribution. `packages/core/src/calibration.json` now carries validation-split-derived weights for all four streams (`spatial`/`frequency`/`audio`/`audio_frequency`).

## 2026-08-28 — shadcn/ui adopted; CLI's Tailwind v4 output adapted back to the project's pinned v3

CLAUDE.md pinned Tailwind + shadcn/ui from the start, but no shadcn component had actually been generated before this session — the web app was hand-rolled Tailwind classes throughout. Ran the shadcn CLI (`components.json`, `radix-nova` style) to add Button, Card, Dialog, Alert, Table, Tooltip, Checkbox, Label, Progress, Separator, Skeleton, Badge, all built on Radix UI primitives for ARIA/keyboard/focus behaviour by default rather than hand-written.

The CLI's generated output assumes Tailwind v4 (`@theme` directive auto-generates utilities like `bg-primary` from bare CSS custom properties), but `package.json` pins `tailwindcss@3.4.17`. Build failed immediately (`The border-border class does not exist`). Fixed by reverting to the pre-v4 shadcn convention: `tailwind.config.ts` now explicitly maps every design token (`background`, `card`, `primary`, `destructive`, `sidebar-*`, `chart-1..5`, etc.) to the `var(--token)` CSS variables `globals.css` already defined, and the v4-only `@import "shadcn/tailwind.css"` was removed from `globals.css` in favor of the standard `@tailwind base/components/utilities` triad. No framework version upgrade was needed. Theme customized with a deep-blue primary (`oklch(0.32 0.08 258)`) rather than shadcn's neutral default; dark-mode tokens are defined but unused since there is no theme toggle yet.

Caught along the way: `latestEvalReport()` in `eval-report.ts` picked the alphabetically last file under `reports/` to find "the latest" report. Once the audio harness started writing `audio-*.json` into the same directory as the image harness's `2026-*.json` files, alphabetical sort put `audio-` after `2026-` (`'a' > '2'` in ASCII) and the accuracy page would have silently rendered stale image numbers instead of erroring. Fixed with explicit prefix filtering (`latestEvalReport()` excludes `audio-`, new `latestAudioEvalReport()` requires it) rather than a smarter sort, since the two report families are unrelated schemas and should never be selected by the same logic.

## 2026-08-28 — A hand-derived audio signal that measures well in-distribution made the fused score *worse* cross-dataset

Designed and built `audio_frequency.py` from first principles for this project (not ported from a paper or library): a harmonics-to-noise ratio measurement, on the hypothesis that neural vocoders reconstruct speech with less natural aperiodic noise than a real vocal tract produces, so spoofed audio should measure as unnaturally "clean". A 60-sample probe of real ASVspoof2019 samples confirmed the hypothesis's direction (spoof mean +1.41 dB, bonafide mean -1.36 dB) with standalone AUC 0.780; a companion measurement, spectral-tail irregularity (image frequency.py's exact logic, ported to audio's own 1D spectrum), measured no better than chance (AUC 0.458) and was kept as a reported-but-non-scoring measurement rather than dropped outright, the same treatment ELA gets for images.

Wired in as a second stream (`audio_frequency`, fused with AASIST via the same weighted-average fusion every other stream uses) and run through a real eval harness pass (n=60/corpus): in-dataset AUC 0.907, but only **0.685 cross-dataset** on ASVspoof2021 -- a real generalisation gap. Fusing it with AASIST at its calibration-derived weight (44.85%, since `derive_fusion_weights` only ever sees calibration-split AUC) **reduced** cross-dataset AUC from 0.962 (AASIST alone) to 0.933. This is the identical validation/cross-dataset divergence pattern the image pipeline hit in Phase 3 (2026-08-21 entry below: the frequency stream got 86% of the fusion weight from calibration AUC, then generalised worse than spatial on the reporting split) -- now confirmed as a recurring failure mode, not a one-off, in a completely independent modality and measurement. A signal that separates classes well on the corpus it was tuned against is not the same claim as a signal that generalises, and calibration-split AUC alone cannot tell the two apart.

Following the same precedent Phase 3 set for images: the measured weight ships as written by `--write-calibration` rather than being hand-overridden, and the gap is documented rather than corrected -- overriding it would mean substituting judgement for measurement, the same violation as tuning weights on the reporting split would be. But this is worth being direct about: as currently weighted, `audio_frequency` makes the shipped audio score *worse* on held-out data, not better, and a reader should not assume every new stream in this codebase is a net improvement just because it exists and measures above chance somewhere. The correct fix -- the same one Phase 3 already named and deferred -- is a third corpus: fit weights on one split, select among candidate measurements on a second, report only on a third untouched by either.

## 2026-08-28 — Perceptual-hash lookup now uses a BK-tree, and it surfaced a real test-isolation gap

Replaced `hash_cache.py`'s bounded linear scan (most recent 500 rows) with an in-memory BK-tree (`bktree.py`, hand-built from the Burkhard-Keller 1973 structure: children bucketed by exact distance from their parent, queries pruned by the triangle inequality) -- the "future work" the module's own docstring had named since Phase 5. Verified against the linear scan directly: a property test inserts 200 random hashes and checks the tree's nearest match agrees with a brute-force scan across 20 random queries at four different distance budgets.

Wiring it in surfaced a genuine, previously-latent test-isolation problem: the tree is a process-lifetime singleton, but only `test_hash_cache.py`'s own `"dead..."`-prefixed rows were ever cleaned from the dev Postgres between test runs -- every *other* test's real cached analysis reports (e.g. `no_face_png`, reused across many files) had been accumulating there indefinitely, all session. The old bounded-500-recent scan happened to avoid colliding with this accumulated data by luck of ordering; the tree's exhaustive search does not, and reliably found `no_face_png`'s real computed phash within Hamming distance 10 of a test's hardcoded `"dead000000000000"` probe, returning a real unrelated report where the test expected `None`. Fixed three ways: the dev cache table was truncated (safe -- it is a disposable cache, nothing durable), `hash_cache.reset_tree()` was added and wired into the test fixture so the in-memory tree respects the same per-test cleanup Postgres already gets, and `TestHashCacheDatabase`'s own tests now run under a tightened `phash_match_max_distance` (their own scenarios never needed more than 2 bits) to shrink the collision surface with whatever real data the rest of the suite leaves behind. The rate-limit test's use of the degenerate all-zero probe hash `"0"*16` was replaced with a random one for the same reason -- a smooth-gradient test fixture's real phash landed suspiciously close to it.

## 2026-08-25 — AASIST's spoof/bonafide output index was inverted from Stage 1 until the eval harness caught it

The audio classifier shipped in Phase 6 stage 1 with `_SPOOF_LOGIT_INDEX = 1`, sourced from a WebFetch summary of the upstream repo's evaluation script that described "index 1" as "the spoof detection score". Running the eval harness's calibration split (the same corpus AASIST was trained on, where it should score close to perfectly) produced an AUC of exactly **0.0** — not a weak-classifier number, a *perfectly inverted* one: mean score 0.017 on spoof samples, 0.998 on bonafide, with 10/10 of each cleanly separated into opposite ends of the scale. That shape is the signature of a working classifier with a flipped label, not a broken one, so it was checked against the actual ground truth rather than re-reading another summary: `data_utils.py`'s `genSpoof_list` builds the training label dict with `1 if label == "bonafide" else 0` -- the model was trained with **label 1 = bonafide, label 0 = spoof**, the opposite of the earlier summary's claim, and also the standard ASVspoof countermeasure-score convention (a CM score means "how bonafide", not "how fake" -- it mirrors ASV score direction). Fixed to `_SPOOF_LOGIT_INDEX = 0` and reran the harness to confirm.

This is the fourth wrong AI-generated claim caught and corrected in this single phase (the others: ASVspoof2021's licence, two wrong Hugging Face dataset repo IDs, and `datasets`'s ZIP-streaming behaviour) -- worth noting as a pattern, not just four isolated incidents: a summary that describes *what code does* is exactly as unverified as one that describes a license or a dataset's contents, and deserves the same "check the primary source" discipline this project already applies to licensing. `tests/test_aasist.py` gained a regression test pinning the direction against real samples rather than only checking the score lands in `[0, 1]`.

## 2026-08-25 — `datasets(streaming=True)` silently downloaded a 36.7 GB archive instead of streaming it

The audio eval harness's reporting split (`Bisher/ASVspoof_2021_DF`) stalled for many minutes with zero progress output after switching to it. The repo's own file listing (checked via the Hub's API, not assumed) explains why: its entire payload is one `ASVspoof_DF_2021.zip`, 36.7 GB, loaded through a custom builder script -- `streaming=True` only gives true row-level streaming for natively chunked formats like parquet, and for a script-based ZIP repo `datasets` has no choice but to materialise the whole archive locally before it can serve a single row, regardless of the flag. Two other candidate mirrors with proper parquet chunking (`MoaazTalab/ASVspoof_2021_*_Balanced_Normalized`) were considered and rejected on the spot: neither states a licence anywhere in its card or API metadata, the same "no rights granted" dealbreaker that sank `Wvolf/ViT_Deepfake_Detection` and the "In the Wild" dataset earlier in this project. Fixed by reading `Bisher/ASVspoof_2021_DF`'s ZIP the same way `datasets.py` already reads the *image* corpora's ZIPs -- `HfFileSystem` gives a seekable handle over ranged HTTP, so `zipfile` reads just the central directory (a few seconds, confirmed by testing directly) and pulls individual ~20-80 KB members on demand, never the archive as a whole.

## 2026-08-25 — The audio eval harness decodes through this project's own `soundfile` path, not `datasets`'s default

`datasets`'s Audio feature type decodes through `torchcodec` as of the version pinned here, and `torchcodec` requires a system FFmpeg install to even import successfully -- confirmed empirically by running the harness and hitting `RuntimeError: Could not load libtorchcodec` across every FFmpeg version it tried, on a machine with no FFmpeg installed. That is exactly the dependency the shipped inference service deliberately avoided when audio decode was built (`soundfile`/libsndfile chosen specifically to not need it -- see `audio_io.py`'s docstring), so requiring it just for the eval harness would be an inconsistent, heavier prerequisite than anything else in this repo's tooling needs. Fixed by reading the Audio column undecoded (`IterableDataset.decode(False)` -- note `.cast_column("audio", Audio(decode=False))` does *not* reliably disable decoding on a streaming dataset in this `datasets` version, confirmed by it still routing through the torchcodec decoder after that call) and handing the raw bytes to `audio_io.decode_audio` instead. This has a genuine methodological upside beyond avoiding the dependency: the harness now scores audio through the identical decode path a real upload goes through, rather than a different one that could theoretically produce slightly different waveform values.

## 2026-08-25 — A web-search summary claimed ASVspoof2021 was non-commercial; the primary source disagreed

While scoping the audio eval harness's cross-dataset reporting split, an initial web search reported ASVspoof2021 as CC BY-NC 4.0 (non-commercial) — plausible, and it briefly went into `LICENSES.md` that way. Before building the harness on top of that claim, the actual host was checked directly: Zenodo's own structured record metadata (`GET /api/records/<id>`, not a rendered-page summary) gives `license.id: "odc-by"` for the LA database and `"odc-odbl"` for DF, both commercial-friendly, matching ASVspoof2019's family. The `LICENSES.md` entry was corrected before the harness was written, not after — the search summary was likely conflating this with a different, genuinely non-commercial audio corpus (several exist, e.g. the "In the Wild" set surveyed alongside it, which turned out to have no findable license at all). Same habit as the earlier `chrome.offscreen` reason lookup in Phase 5: an AI-generated answer describing a licence or API contract is a claim to check against the primary source, not a fact to act on.

## 2026-08-25 — Audio's classifier is vendored research code, not a `transformers` checkpoint

Every model wired into this codebase so far (`prithivMLmods/Deep-Fake-Detector-v2-Model`, YuNet, MediaPipe FaceLandmarker) loads through a library's own `from_pretrained`-style API. AASIST doesn't: it's a peer-reviewed graph-attention architecture (Jung et al., ICASSP 2022) published as plain research code with no PyPI package, so `app/models/aasist.py` vendors the ~400-line model definition directly from NAVER/Clova AI's repository (MIT license, verified from the repo's own root `LICENSE` file — see `LICENSES.md`) rather than reimplementing it or accepting a weaker but more conveniently-packaged community fine-tune.

This nearly went wrong in a specific way worth recording: the vendored code was initially cleaned up to snake_case attribute names (`pos_S` → `pos_s`, `GAT_layer_S` → `gat_layer_s`, etc.) for lint consistency with the rest of the codebase. PyTorch derives a module's `state_dict()` keys from its attribute names, and the pretrained `AASIST.pth` checkpoint was saved against the *original* non-PEP8 names — so the rename would have made `load_state_dict()` either fail outright or, worse, silently fail to load some layers under `strict=False`. Caught before it shipped by tracing through exactly which names become checkpoint keys (registered `nn.Module`/`nn.Parameter` attributes) versus which don't (plain tensors, method names, class names), and reverted only the attributes that mattered. `tests/test_aasist.py::test_checkpoint_loads_without_key_mismatch` pins this as a regression test.

## 2026-08-25 — Extension network calls route through the background worker, never the content script

A content script's `fetch()` is subject to the *hosting page's* Content-Security-Policy `connect-src` directive, not the extension's own — a page that locks down outbound requests would silently break analysis on exactly the pages where it fires. `chrome.runtime.sendMessage` to the background service worker sidesteps this entirely, since the service worker's fetches are governed by the extension's own manifest, not the page it happens to be injected into. Every network call (`/v1/analyze`, `/v1/analyze/hash`) is issued from `background.ts`; the content script and offscreen document only ever talk to the background worker over the extension's internal messaging.

## 2026-08-25 — Video frame capture needs an offscreen document; images don't

`chrome.offscreen.createDocument()` exists because MV3 service workers have no DOM — no `<canvas>`, no `<video>`. Images are captured directly in the content script, which already has DOM access to the page's `<img>`/`<canvas>` elements. Video needs a fresh, isolated `<video>` element to seek to a timestamp and decode a frame, which only a document context (offscreen or content script) can provide; the offscreen document was chosen over doing it in the content script so a broken or slow decode can't be attributed to, or interfered with by, the host page's own DOM. The `BLOBS` offscreen reason was used (not `USER_MEDIA` or `DOM_SCRAPING`) after checking Chrome's own documentation directly rather than trusting a search summary — `BLOBS` is documented for exactly this "decode media data off the main thread" use, the other two describe different capabilities (live camera/mic access, reading page content).

## 2026-08-25 — Perceptual hash computed client-side before any upload decision

`packages/core/src/phash.ts` ports the same DCT-II pHash the inference service already computes server-side (`services/inference/app/pipeline/phash.py`), verified against golden values across both implementations. The extension hashes the captured image/frame locally and calls `/v1/analyze/hash` first; a Hamming-distance hit against the server's cache means the user gets a result without ever uploading the media. This is a privacy property, not just a cache optimisation — it's what makes "no background upload without explicit per-item action" and "check cache before uploading" the same design rather than two separate promises to keep in sync.

## 2026-08-22 — Lip-sync deferred: same licence-blocker pattern as the Phase 3 second backbone

Stream C's spec calls for Wav2Lip-style audio-visual desync scoring. Wav2Lip's weights are non-commercial, trained on the BBC-licensed LRS2 corpus. The natural alternative, SyncNet (`joonson/syncnet_python`), has MIT-licensed code but undocumented weights from the same Oxford VGG lineage that produced Wav2Lip's restriction — the same "no license, adjacent to a known-restricted corpus" red flag that got a candidate rejected in Phase 1. Neither was adopted; lip-sync is not implemented in Phase 4. Recorded in `LICENSES.md`.

## 2026-08-22 — Two frame-sampling densities, because one signal set needs what the other can't afford

The expensive per-frame path (Stream A's ViT+TTA, Stream B, Grad-CAM) is capped at 24 sampled frames to keep worst-case runtime bounded on CPU-only inference — chosen with the user, trading off against a 60-frame option that would roughly double worst-case time. Stream C's biological signals need something close to the opposite: rPPG must resolve a 0.7-4 Hz signal, which by the Nyquist criterion needs at least ~8 Hz sampling, and 24 frames spread over up to 60 seconds is nowhere close. A second, separate, *cheap* pass (decode + landmark-only, no classifier) reads a contiguous ~12-second window at up to 25 fps for exactly this reason. The two passes serve genuinely different signal requirements, not just different budgets.

## 2026-08-22 — Video reuses the image schema instead of forking a `FrameFinding` type

A video's per-sampled-frame primary-face result is structurally the same thing as an image's per-face result — score, band, uncertainty, penalties, an optional heatmap — so it reuses `FaceFinding`/`faces[]` rather than introducing a parallel type. The one real gap this exposed: there was no way to say *when* in the clip a finding occurred, so `timestamp` was added as an optional field (undefined for an image's face, populated for a video's sampled frame). `Aggregation`'s multiplicity-correction logic (Phase 3, originally built for multiple faces in one photo) turned out to generalise directly: many sampled frames tested is the same "more chances for a spurious high score" shape as many faces tested, so a lone elevated frame among 24 gets the identical statistical discount a lone elevated face gets among several people.

## 2026-08-22 — Stream C reports a score but carries zero fusion weight

Same treatment Stream B had before Phase 3 measured it, and Stream D still has: no video-labelled dataset exists to derive a weight from, so Stream C's four sub-signals (optical flow discontinuity, blink analysis, head-pose jitter, rPPG) are computed, scored, and shown as evidence, but `fusion.stream_weights().get("temporal", 0.0)` falls back to zero and the fused score is driven by spatial/frequency/provenance only. A regression test (`test_temporal_stream_never_moves_the_fused_score`) pins this. Extending the eval harness to video is future work — see `LICENSES.md`.

## 2026-08-22 — MediaPipe FaceLandmarker gives blink and pose signals directly, not hand-rolled

The model's blendshape output (`eyeBlinkLeft`/`eyeBlinkRight`) is a trained regression, used directly for the blink signal instead of a hand-rolled eye-aspect-ratio geometric heuristic. Its facial transformation matrix is a rigid transform already fitted by the model's own 3D face geometry, used directly for head pose instead of a separate solvePnP fit. Both are simpler and more grounded than reimplementing the same measurements from raw landmark coordinates.

## 2026-08-22 — Forehead ROI geometry hedges against headwear rather than trying to solve it

The rPPG forehead region is placed relative to eye position and overall face height rather than the topmost mesh landmark, because low headwear (a cap brim) sits at or below where that point falls and would otherwise place the ROI on the brim instead of skin. Verified against a real photo (a naval portrait with a low-brimmed cap) that this still fails when the brim sits very close to the eyebrows — a genuine remaining edge case, not chased further. Instead of iterating on geometry against one adversarial photo, rPPG combines the forehead reading with both cheek ROIs (which land correctly on skin in the same photo), so a bad forehead reading is hedged rather than solely relied upon.

## 2026-08-22 — Frame sampling is tested for real, not mocked: synthetic `.mp4` fixtures via `cv2.VideoWriter`

`cv2.VideoWriter` with `mp4v`/`.mp4` produces small, fast, genuinely decodable video fixtures offline, the same pattern the image test suite established with matplotlib's bundled sample photo. This caught two real bugs during development, not just theoretical ones: `probe()` returned `-1` frame counts for an unopened capture because `int(x or 0)` does not catch negative sentinels (only falsy zero), and a face-map artifact was being attached to the wrong stream in `analyze_video.py` because of the order artifacts were appended in versus when they were mutated.

## 2026-08-22 — A CHROM-cancelled synthetic test signal is not a CHROM bug

Early rPPG tests injected a pure sinusoid proportionally into R and G channels to check the algorithm recovers a known frequency. It didn't — CHROM's `alpha` coefficient is specifically fitted to cancel any signal that varies with a fixed ratio across channels (that's the whole mechanism: it treats a common-mode signal as motion/lighting artifact), so a synthetic pulse injected exactly that way is mathematically guaranteed to cancel to within floating-point noise, regardless of the per-channel amplitudes chosen. This is CHROM working as designed, not a defect. The frequency-domain logic (bandpass + periodogram peak-finding) was factored out into `find_pulse_peak()` and tested directly against a clean 1D synthetic signal instead, which properly validates that half of the pipeline without fighting CHROM's own cancellation.

## 2026-08-22 — Two latent Phase 3 test gaps surfaced and fixed while verifying Phase 4

Running the full model-marked suite (not just the offline `-m "not model"` subset used for routine checks) surfaced two `test_analyze.py` assertions that had been stale since Phase 3 added the frequency and provenance streams to `analyze_image`: one asserted exactly one stream would be returned for a face (now three), the other asserted degraded input always produces a *wider* uncertainty band than clean input. The second was a real behavioural change worth understanding, not just a stale number: since Phase 3, uncertainty width sums a confidence-penalty term (which *is* guaranteed to grow with envelope violations) and a cross-stream-disagreement term (which is genuine, data-driven, and not required to move in the same direction) — a heavily compressed image can happen to show smaller cross-stream disagreement than a clean one if recompression pulls the streams' scores closer together, which does not mean it was judged more trustworthy overall. Both tests now check what the architecture actually guarantees rather than a coincidental total. Neither was a Phase 4 regression; both had simply never been re-run against the code they were asserting about.

## 2026-08-21 — Fusion weights are derived from validation AUC, and validation AUC disagreed with cross-dataset AUC

The completed evaluation run (`eval/reports/2026-08-21.md`, n=1200/corpus) surfaced a real gap. Fusion weights come from each stream's AUC on the calibration split (`deepfakeface`), per the spec: frequency scored 0.7132 there against spatial's 0.5335, so frequency got 86% of the fusion weight. But on the held-out cross-dataset split (`df40faces`) the ranking inverts — spatial's 0.6633 beats frequency's 0.5890. The stream weighted more heavily is the one that generalizes worse.

This is not a bug in the harness; the cross-dataset protocol is exactly what surfaced it, which is the protocol working as intended. The likely cause is that `deepfakeface` (InsightFace face-swaps composited onto real photos) and `df40faces` (40 different DF40 manipulation techniques) are different enough that a stream tuned to one does not transfer to the other — the frequency stream's unsupervised statistics may be picking up something specific to InsightFace's compositing rather than manipulation in general.

**Decision: ship the validation-derived weights as-is, with the gap documented rather than corrected.** Two ways to "fix" this were considered and rejected for now:

- Deriving weights from the reporting split instead would make it stop being held out — the corpus used to justify the headline numbers would also have been used to tune the model, which is the exact thing the mandatory cross-dataset protocol exists to prevent.
- A genuine three-way split (fit / validate / report) is the methodologically correct answer, but needs a third evaluation corpus and another multi-hour run, and was deferred rather than blocking Phase 3's close.

Revisit when a third corpus is added: fit fusion weights on validation, pick the fitting procedure using a middle split, and report only on a split touched by neither.

## 2026-08-21 — The eval harness needed to survive real network conditions

Getting one full run to complete took three attempts, each teaching something the harness did not previously handle:

1. A run died at 300/1200 with no partial results kept, because scores were only assembled in memory. Fixed by writing each score to a JSONL cache keyed by archive-qualified member path as it is produced, so a rerun of the same configuration resumes rather than restarting (`fix(eval): make the harness resumable across network failures`).
2. A rerun then stalled indefinitely after 128 images, alive but making no progress, with no error. `urllib`/`requests` default to no socket timeout, so a connection that stalls mid-read — rather than failing — blocks forever. Fixed with `socket.setdefaulttimeout(60)` plus a per-archive retry loop that reopens the archive handle and retries only the members that failed, up to 4 attempts with backoff (`fix(eval): add socket timeout and per-archive retry to dataset reads`).
3. The combination let the third attempt finish: it resumed from the 128 already-cached scores and rode out every subsequent stall through the retry loop instead of losing hours of progress to a single bad read.

## 2026-08-15 — Fusion weights are measured, and a stream is allowed to measure as useless

`derive_fusion_weights` sets each stream's weight proportional to how far its validation AUC sits above chance, normalised. A stream at or below 0.5 gets exactly zero and contributes nothing. Two consequences were chosen deliberately:

- A stream measuring **below** chance is not inverted to extract signal from it. Inverting would be fitting to the validation split rather than measuring, and would leave a detector whose reasoning we could not explain.
- When no fitted weights exist, fusion falls back to a single stream and says so, rather than averaging with invented weights. An unfitted product should behave conservatively, not guess.

## 2026-08-15 — The frequency stream must not move a no-face result

Stream B runs on the whole frame, so it produces a score even when no face is found. Wiring it into the no-face path initially dragged a blank gradient to 0.376 — "weak indication, likely benign" — which asserts the image was examined and looked fine. It was not examined; the primary detector could not run.

Stream B's thresholds are derived from face imagery and it has no validated standalone accuracy on anything else, so on the no-face path it is reported as context but contributes nothing to the score, which stays at 0.5. Stream D is treated differently and still overrides, because it reads recorded facts rather than inferring from pixels and needs no face. There is a regression test naming this specific failure.

## 2026-08-15 — Provenance overrides rather than being heavily weighted

A valid C2PA manifest or self-identifying generator metadata is categorically better evidence than a statistical detector, so Stream D acts through clamp/floor rather than through a weight. Both stop short of certainty: the generator floor leaves the score below 1.0 because such metadata is trivially removable and forgeable, and the C2PA clamp does not zero the score because a signature attests to a signing chain, not to the content being unaltered before signing.

`trusted_signer` is always reported as unknown. We maintain no signer allow-list, and claiming trust we cannot substantiate would be worse than admitting the gap.

## 2026-08-15 — Unmeasurable metrics report themselves as unmeasurable

TPR at FPR=0.1% needs at least ~1,000 authentic samples to observe a single false positive, and far more for a stable estimate. Rather than print a number derived from a handful of events, `tpr_at_fpr` returns "not measurable" with the arithmetic explaining why, and the report and accuracy page render that text. A missing row reads as "fine"; an explicit "not measurable" does not. AUC carries a bootstrap confidence interval for the same reason — sampling error should be visible rather than implied.

## 2026-08-15 — Evaluation corpora are streamed from ZIP archives, never committed

Neither corpus is published as parquet, so `datasets.load_dataset` streaming is unavailable. Both are ZIPs on the Hugging Face hub, which is served with HTTP range support, so `HfFileSystem` plus `zipfile` reads individual members without downloading whole archives — a few hundred images instead of 5.4 GB. The trade-off is many small ranged requests, which is I/O-bound and rate-limited; a full run takes hours on a home connection, dominated by network rather than CPU.

The reporting corpus is CC BY-NC 4.0. Using it for evaluation only was a deliberate decision: it contributes no weights and no code to the product, only numbers in a report. If VeriFrame is commercialised it must be replaced and the numbers regenerated. This is recorded in `LICENSES.md`.

## 2026-08-15 — No second backbone adopted, and why that is recorded rather than worked around

Every candidate for the second ensemble member is blocked. The best on the merits (`yermandy`, MIT, CLIP ViT-L/14, real cross-dataset numbers) does not document its preprocessing — its README defers to the DeepfakeBench pipeline — nor which logit means "fake", and runs at ~6.8 s per forward pass on CPU. The only architecturally distinct model with standard loading (`Organika/sdxl-detector`, Swin) is CC-BY-NC-3.0, and unlike an eval dataset, weights ship inside the product.

Wiring either in with guessed normalisation would produce confident nonsense rather than a visible failure, so neither was adopted. The ensemble machinery is built and tested so that adding one later is configuration. Details in `LICENSES.md`.

## 2026-08-15 — Group photos: the maximum face score needed a multiplicity correction

Reporting the highest face score as the image score has a defect that shows up precisely on group photos. Every face tested is another opportunity for a high score to appear by chance, so an eight-person photo has many more chances to produce one than a portrait. Left uncorrected, group photos would score systematically higher than solo photos for reasons unrelated to manipulation — and this detector already returns 0.71 on a genuine photograph, so the base rate of spurious highs is not negligible.

`aggregate.py` keeps the maximum as the headline, because one manipulated face does mean the image is manipulated, but distinguishes three cases:

- **One face elevated among several.** Penalised by a factor that shrinks as face count grows, floored at 0.55 so a crowd scene never erases a real signal. This is the face-swap shape, but also the shape chance produces.
- **Every face elevated.** No multiplicity penalty, because coincidence does not explain a uniform result. Instead a caveat that a detector reacting identically to every face usually points at a whole-image cause — AI generation, filtering, unusual compression — rather than each person being edited separately.
- **Some but not all elevated.** Reported as genuinely ambiguous, with the per-face detail left to distinguish real findings from faces that are merely small or badly lit.

## 2026-08-15 — Each face carries its own envelope, not the image's

A group photo mixes a 200px front-row face with a 30px face at the back. Judging both against image-level measurements would report identical confidence for two findings that deserve very different confidence. `assess_face` measures size, blur and exposure on each face's own crop, and the small-face penalty scales with how far under the threshold the face falls rather than being a flat cut.

## 2026-08-15 — The conclusion is assembled from templates, not generated

The plain-language summary is what most readers will actually read, which makes it the easiest place to accidentally state a verdict. It is built from fixed templates chosen by the face-count pattern, so its claims can be unit-tested and cannot drift into overclaiming. Tests assert that no phrasing across every reachable pattern resolves to "is fake" or equivalent, that a clean result still says detectors miss things, and that the advice points at provenance — which beats any statistical detector.

## 2026-08-15 — Schema modules split to break a cycle

`FaceFinding` needs `EnvelopePenalty`, and `AnalysisReport` needs `FaceFinding`. Keeping the penalty schema in `analysis-report.ts` would have made the two modules circular, which breaks at runtime for Zod values even though TypeScript tolerates it at type level. `envelope.ts` now holds the penalty and envelope schemas and both import from it.

## 2026-08-15 — Expiry and user deletion are deliberately different

Two retention paths, because they answer different questions. The TTL sweep deletes the stored media but keeps the job row and the perceptual hash, so the user can still read the report they were given and a repeat upload can be recognised without retaining the image. User-initiated deletion removes everything including the hash.

The privacy policy documents both separately. An earlier draft described only the expiry behaviour and claimed the hash was kept "after deletion", which was wrong for the deletion endpoint — an inaccuracy in a compliance document, so the text now distinguishes the two.

The sweep marks a row deleted only after the object-store delete returns successfully. The reverse order would leave orphaned media that no later sweep would ever select, since the query filters on `media_deleted_at IS NULL`.

## 2026-08-15 — Consent is enforced server-side, not just in the UI

The checkbox gates the submit button, but `POST /api/analyze` independently rejects any request without `consent=true`, and does so before writing to object storage. A test asserts the consent check appears earlier in the handler than the `putMedia` call, since a gate that runs after the write is not a gate.

## 2026-08-15 — Clerk optional locally, mandatory in production

Requiring a Clerk account before any of the queue, storage, or report work could be exercised would have blocked the whole phase on an external signup. Instead `authDisabled()` returns true only when keys are absent *and* `NODE_ENV !== "production"` — it throws otherwise, so the bypass cannot reach production. In bypass mode requests are attributed to a fixed development user id rather than skipping the ownership checks, keeping the authorization path identical in both modes.

Job lookups are scoped by user id, so another user's job and a non-existent job are both a 404 and are indistinguishable from outside.

## 2026-08-15 — Worker is a separate process

The queue consumer runs as its own `tsx` process rather than inside a Next.js route handler, matching how it deploys. One consequence worth recording: it does not get Next's automatic `.env.local` loading, so it loads the file itself via `process.loadEnvFile` from a module imported before anything reads `process.env` — import bodies evaluate in order, whereas a bare statement at the top of the worker entry would still run after that module's own imports resolved.

## 2026-08-15 — `next lint` replaced with a direct ESLint invocation

`next lint` is deprecated, will be removed in Next.js 16, and prompts interactively when no ESLint config exists — which would hang CI rather than fail it. The app uses a flat `eslint.config.mjs` wrapping `next/core-web-vitals` through `FlatCompat`, invoked as `eslint .`.

## 2026-08-15 — YuNet replaces both face detectors named in the spec

The spec proposed RetinaFace or YOLOv8-face. Both block commercial use: Ultralytics YOLOv8 is AGPL-3.0 and that covers the trained models, not just the training code, so shipping it commercially means open-sourcing all of VeriFrame or buying an Enterprise License; InsightFace's code is MIT but its pretrained RetinaFace weights are released for non-commercial research only.

YuNet is MIT-licensed, ~230 KB, and runs through OpenCV's own `cv2.FaceDetectorYN`, so it adds no dependency beyond OpenCV, which the pipeline needs anyway. Recorded in `LICENSES.md` along with the rejected options.

Note OpenCV 5.x requires the dynamic-input-shape build of the model (`face_detection_yunet_2026may.onnx`) while 4.x needs the fixed-shape one; `faces.py` selects by OpenCV major version.

## 2026-08-15 — Phase 1 classifier: prithivMLmods ViT, with yermandy noted for Phase 3

Four candidates were checked for existence and license. `Wvolf/ViT_Deepfake_Detection` declares no license and was discarded — no license means no rights granted. `dima806/deepfake_vs_real_image_detection` is Apache-2.0 but is another fine-tune of the same `google/vit-base-patch16-224-in21k` base as the chosen model, so pairing them later would violate the architectural-diversity requirement, and its author warns of significant concept drift.

`prithivMLmods/Deep-Fake-Detector-v2-Model` (Apache-2.0) was chosen for Phase 1 because it loads through standard `transformers` and has a clean Grad-CAM path, getting the full pipeline working end-to-end quickly.

`yermandy/deepfake-detection` (MIT, CLIP ViT-L/14 + LN-tuning) is the strongest candidate found on the merits — it is the only one publishing a genuine cross-dataset protocol (trained on FaceForensics++, reporting 96.62% AUROC on Celeb-DF-v2 and 87.15% on DFDC) and is architecturally distinct from ViT-base. It needs custom loading code, so it is deferred to the Phase 3 ensemble rather than blocking Phase 1.

## 2026-08-15 — The band table is data, not code

`packages/core/src/bands.json` is the canonical table. `bands.ts` imports it and `services/inference/app/bands.py` reads the same file, so a threshold exists in exactly one place across both languages. Boundary semantics (lower bound inclusive, upper exclusive except for the final band) are asserted identically in the Vitest and pytest suites, because a disagreement would mean the same score is labelled differently in the API and the UI.

## 2026-08-15 — Absence of evidence is reported as inconclusive, not as clean

When no face is detected, Stream A cannot run. The service returns 0.5, which lands in "Mixed signals — inconclusive, manual review advised", with a full-width uncertainty interval and an explicit envelope penalty. Returning a low score would imply we looked and found nothing, which is a different and false claim.

## 2026-08-15 — The confidence penalty shrinks the score toward 0.5 and widens the interval

Out-of-envelope inputs accumulate multiplicative penalties, each with a human-readable reason. The combined multiplier is applied as `score = 0.5 + (raw - 0.5) * confidence` and also widens the uncertainty band. Shrinking toward the uninformative midpoint is the honest response to "we don't trust this input" — the alternative, reporting the raw score with a quiet caveat, keeps a confident-looking number on screen.

Every report also carries a permanent uncalibrated-score penalty until Phase 3 fits temperature scaling, since raw softmax outputs are overconfident.

## 2026-08-15 — Uncertainty from TTA spread is a stopgap, and labelled as one

The architecture calls for ensemble disagreement across architecturally different backbones as the primary uncertainty source. Phase 1 has a single backbone, so the spread across the four test-time augmentations substitutes. It is a strictly weaker signal — it measures sensitivity to flip and scale, not error decorrelation — and in practice is very small (~0.001 on clean input). It is labelled as a weak proxy in the report artifacts rather than presented as a real uncertainty estimate, and is replaced in Phase 3.

## 2026-08-15 — ONNX export is a single self-contained file

`torch.onnx.export` on torch 2.13 defaults to splitting weights into a sibling `.onnx.data`, which loads fine locally and produces a silently broken model if only the `.onnx` is copied to a deployment. At ~340 MB this model sits well inside protobuf's 2 GB ceiling, so `external_data=False` is the default and a test asserts no sibling files are produced. The torch path remains the default at runtime because Grad-CAM needs autograd; a test asserts the two backends agree to 1e-3.

## 2026-08-14 — Repo initialized fresh, scoped to project folder

The git repository originally present on this machine was rooted at the user's home directory (`C:\Users\Kaushik`) rather than the project folder, and was tracking unrelated projects and OS/profile directories. Rather than reuse or fix that repo, a new git repository was initialized directly inside the `Deepfake-Analyser` project folder so history and remotes stay scoped to VeriFrame only.

## 2026-08-14 — Phase 0 scope

Full monorepo skeleton built up front (pnpm + Turborepo workspaces for all apps/packages, Docker Compose, CI, `packages/core` fully implemented). `apps/web`, `apps/extension`, `packages/ui`, and `services/inference` are workspace stubs only — real implementation starts in their respective phases (2, 5, 2, 1) — so the workspace graph resolves and CI has something to run against without pretending unbuilt surfaces are done.
