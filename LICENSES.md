# Licenses

Tracks licensing for every third-party dataset, pretrained model, and detection-relevant dependency, and whether it blocks commercial use. Every entry here was checked against the upstream source before the dependency was wired in.

## In use

| Name | Type | License | Commercial use? | Notes |
|---|---|---|---|---|
| [`prithivMLmods/Deep-Fake-Detector-v2-Model`](https://huggingface.co/prithivMLmods/Deep-Fake-Detector-v2-Model) | Model (ViT-base image classifier) | Apache-2.0 | ✅ Yes | Stream A classifier. Fine-tune of `google/vit-base-patch16-224-in21k`. Self-reported 92.12% accuracy is **in-dataset only** — no cross-dataset protocol published, so it is not quoted anywhere in the product. Pinned to commit `3a99ae2`. |
| [YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) | Model (face detector, ~230 KB ONNX) | MIT | ✅ Yes | Run via OpenCV's `cv2.FaceDetectorYN`. Authors: Wu Wei, Peng Hanyang, Yu Shiqi. |
| OpenCV (`opencv-python-headless`) | Library | Apache-2.0 | ✅ Yes | Decode, face detection runtime, DCT for pHash, envelope measurements. |
| [`grad-cam`](https://github.com/jacobgil/pytorch-grad-cam) | Library | MIT | ✅ Yes | Heatmap artifacts. |
| PyTorch / Transformers / ONNX Runtime | Libraries | BSD-3-Clause / Apache-2.0 / MIT | ✅ Yes | Model runtime and export. |
| [MediaPipe](https://github.com/google-ai-edge/mediapipe) + [`face_landmarker`](https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task) | Library + model (478-point face mesh, blendshapes, pose) | Apache-2.0 | ✅ Yes | Stream C landmarks, blink signal (blendshapes), and head pose (transformation matrix). Both the library and the model bundle are Google's own, same terms. |
| SciPy | Library | BSD-3-Clause | ✅ Yes | Stream C's rPPG: Butterworth bandpass filtering and periodogram peak-finding. |

## Evaluation datasets

Used only by `services/inference/eval/`. They contribute no weights and no code to the shipped product — only numbers in a report. Neither is committed to this repository; both are streamed from the Hugging Face hub at eval time.

| Name | License | Commercial use? | Role | Notes |
|---|---|---|---|---|
| [`OpenRL/DeepFakeFace`](https://huggingface.co/datasets/OpenRL/DeepFakeFace) | Apache-2.0 | ✅ Yes | Calibration split | Real celebrity photographs (IMDB-WIKI) vs faces swapped with InsightFace. |
| [`pujanpaudel/deepfake_face_classification`](https://huggingface.co/datasets/pujanpaudel/deepfake_face_classification) | **CC BY-NC 4.0** | ⚠️ **No** | Reporting split | Fakes drawn from the DF40 test split (40 manipulation techniques). **Non-commercial.** Evaluation-only use was a deliberate decision — see `DECISIONS.md`. If VeriFrame is commercialised, this corpus must be replaced with a permissively licensed one and the numbers regenerated. |

## Rejected — commercial-use blockers

These were named as candidates in the original project spec. Both were rejected after checking their terms.

| Name | License | Why rejected |
|---|---|---|
| [Ultralytics YOLOv8-face](https://www.ultralytics.com/license) | AGPL-3.0 | AGPL-3.0 covers the trained models as well as the training code. Using it commercially requires either open-sourcing all of VeriFrame under AGPL-3.0 or purchasing an Ultralytics Enterprise License. Replaced by YuNet. |
| [InsightFace RetinaFace](https://github.com/deepinsight/insightface/issues/2022) | Code MIT, **weights non-commercial** | The library code is MIT, but the pretrained weights — both manual and auto-downloaded — are released for non-commercial research purposes only. Replaced by YuNet. |
| [`Wvolf/ViT_Deepfake_Detection`](https://huggingface.co/Wvolf/ViT_Deepfake_Detection) | **None stated** | The model page declares no license, so no rights are granted to use it. Not used. |
| [Wav2Lip](https://github.com/Rudrabha/Wav2Lip) | Code: non-commercial/research only | The architecture's Stream C spec calls for Wav2Lip-style audio-visual desync scoring. Wav2Lip's own README states it is licensed for personal/research/non-commercial use only, because its weights are trained on the LRS2 corpus, which is BBC-copyrighted and restricted to non-commercial research under a separate BBC data agreement. Lip-sync analysis is not implemented in Phase 4 as a result — see the entry below and `services/inference/app/pipeline/temporal.py`. |
| [`joonson/syncnet_python`](https://github.com/joonson/syncnet_python) (SyncNet) | Code MIT, **weights undocumented** | The natural alternative to Wav2Lip for the same signal. Its *code* is MIT, but its pretrained weights carry no stated license or documented training-data provenance, and it comes from the same Oxford VGG research lineage that produced the LRS2-restricted Wav2Lip model — the same "no license, adjacent to a known-restricted corpus" pattern that got `Wvolf/ViT_Deepfake_Detection` rejected above. Not used. |

## Second ensemble backbone — evaluated, none adopted

The architecture calls for several architecturally different backbones so their errors decorrelate. Every candidate checked is blocked by licence or by a missing specification; none was adopted, because a model wired in with guessed preprocessing produces confident nonsense rather than a visible failure.

| Name | License | Architecture | Why not adopted |
|---|---|---|---|
| [`yermandy/deepfake-detection`](https://huggingface.co/yermandy/deepfake-detection) | MIT | CLIP ViT-L/14 | Best on the merits — the only candidate publishing a genuine cross-dataset protocol (FF++ → 96.62% AUROC on Celeb-DF-v2, 87.15% on DFDC), and it ships a `model.torchscript` that loads without custom code. **But** its README states images must be preprocessed through the DeepfakeBench pipeline, and neither the normalisation constants nor which of its two logits means "fake" are documented. Its published figures are also *video-level*, aggregated over frames, which is not the task we would use it for. Separately, it takes ~6.8 s per forward pass on this CPU — roughly 6× the current model — which makes it impractical for interactive use without a GPU. |
| [`Organika/sdxl-detector`](https://huggingface.co/Organika/sdxl-detector) | **CC-BY-NC-3.0** | Swin | Genuinely different architecture, standard `transformers` loading, unambiguous labels. Rejected purely on licence: unlike an evaluation dataset, model weights ship inside the product, so non-commercial weights would block commercial use of VeriFrame entirely. |
| [`dima806/deepfake_vs_real_image_detection`](https://huggingface.co/dima806/deepfake_vs_real_image_detection) | Apache-2.0 | ViT-base | Licence is fine and loading is trivial, but it is another fine-tune of the same `google/vit-base-patch16-224-in21k` base as the model in use, so pairing them gives correlated errors — the opposite of what an ensemble is for. Author also warns of significant concept drift since training. |

The ensemble machinery (multi-model registry, cross-stream disagreement as the uncertainty source, weight derivation per stream) is built and tested, so adding a backbone is configuration once a suitable one exists.

## Datasets not yet used

FaceForensics++, Celeb-DF-v2, DFDC, and WildDeepfake — the corpora the original spec named for the eval harness — each require a signed research agreement, are research-only, and must not be committed to this repository. `services/inference/eval/` currently uses `OpenRL/DeepFakeFace` and `pujanpaudel/deepfake_face_classification` instead (see "Evaluation datasets" above); these four remain candidates for extending the harness, and their terms will be recorded here before any of them is used.

## No video evaluation dataset yet

Stream C (temporal/biological signals) has no video-labelled dataset to measure against, so unlike Streams A and B it carries no eval-derived fusion weight — it is reported for evidence only. Extending the eval harness to video and picking a licensable video deepfake corpus is future work.
