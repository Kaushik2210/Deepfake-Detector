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

## Rejected — commercial-use blockers

These were named as candidates in the original project spec. Both were rejected after checking their terms.

| Name | License | Why rejected |
|---|---|---|
| [Ultralytics YOLOv8-face](https://www.ultralytics.com/license) | AGPL-3.0 | AGPL-3.0 covers the trained models as well as the training code. Using it commercially requires either open-sourcing all of VeriFrame under AGPL-3.0 or purchasing an Ultralytics Enterprise License. Replaced by YuNet. |
| [InsightFace RetinaFace](https://github.com/deepinsight/insightface/issues/2022) | Code MIT, **weights non-commercial** | The library code is MIT, but the pretrained weights — both manual and auto-downloaded — are released for non-commercial research purposes only. Replaced by YuNet. |
| [`Wvolf/ViT_Deepfake_Detection`](https://huggingface.co/Wvolf/ViT_Deepfake_Detection) | **None stated** | The model page declares no license, so no rights are granted to use it. Not used. |

## Evaluated, not yet used

| Name | License | Notes |
|---|---|---|
| [`yermandy/deepfake-detection`](https://huggingface.co/yermandy/deepfake-detection) | MIT | CLIP ViT-L/14 with LN-tuning. The only candidate found with a published **cross-dataset** protocol (trained on FaceForensics++, reporting 96.62% AUROC on Celeb-DF-v2 and 87.15% on DFDC). Strongest candidate for the Phase 3 ensemble, and architecturally distinct from the current ViT-base, which matters for error decorrelation. Requires custom loading code rather than plain `transformers`. |
| [`dima806/deepfake_vs_real_image_detection`](https://huggingface.co/dima806/deepfake_vs_real_image_detection) | Apache-2.0 | Also a `google/vit-base-patch16-224-in21k` fine-tune, so pairing it with the current model would violate the architectural-diversity requirement. Author warns of significant concept drift since training. |

## Datasets

None in use. Phase 3 introduces the eval harness; FaceForensics++, Celeb-DF-v2, DFDC, and WildDeepfake each require a signed research agreement, are research-only, and must not be committed to this repository. Their terms will be recorded here before any of them is used.
