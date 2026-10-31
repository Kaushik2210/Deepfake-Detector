"""Fine-tune the spatial image classifier on DeepFakeFace, for a GPU session (Colab/Kaggle).

Run from services/inference with the package installed (`pip install -e .`):

    python -m training.finetune_spatial --out ./finetuned-spatial --per-class 3000 --epochs 3

Leakage rules (this is what keeps the later numbers defensible):

* Trains only on `deepfakeface` (Apache-2.0). `df40faces` is the reporting corpus
  and is never read here; it is also CC BY-NC, so it must not contribute weights.
* Excludes the exact 2000 images calibration was fitted on (`seed=0`), so the
  temperature fitted afterwards is not computed on training data.
* Early stopping uses a validation slice carved from the training pool, never the
  reporting corpus.

After training, point `SPATIAL_MODEL_ID` at the output directory and re-run
`python -m eval.run` unchanged. Whatever it measures is what gets reported.
"""

from __future__ import annotations

import argparse
import io
import random
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from transformers import AutoImageProcessor, AutoModelForImageClassification

from app.config import get_settings
from app.models.registry import _resolve_positive_index
from eval.datasets import DATASETS, load_samples, selected_keys

CALIBRATION_LIMIT = 2000
CALIBRATION_SEED = 0
STORE_SIZE = 256


def _augment(image: Image.Image, rng: random.Random) -> Image.Image:
    # Recompression and rescaling are what real media goes through; training on
    # them is the main lever against the q60/q30 collapse seen in the eval report.
    if rng.random() < 0.5:
        image = image.transpose(Image.FLIP_LEFT_RIGHT)
    if rng.random() < 0.5:
        scale = rng.uniform(0.5, 1.0)
        size = max(64, int(image.width * scale))
        image = image.resize((size, size), Image.BILINEAR)
    if rng.random() < 0.6:
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=rng.randint(30, 95))
        buffer.seek(0)
        image = Image.open(buffer).convert("RGB")
    return image


class _Faces(Dataset):
    def __init__(self, items, processor, positive_index, negative_index, augment, seed=0):
        self.items = items
        self.processor = processor
        self.positive_index = positive_index
        self.negative_index = negative_index
        self.augment = augment
        self.rng = random.Random(seed)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, i: int):
        image, label = self.items[i]
        if self.augment:
            image = _augment(image, self.rng)
        pixels = self.processor(images=image, return_tensors="pt")["pixel_values"][0]
        target = self.positive_index if label == 1 else self.negative_index
        return pixels, target


def _load_pool(per_class: int):
    spec = DATASETS["deepfakeface"]
    exclude = selected_keys(spec, CALIBRATION_LIMIT, CALIBRATION_SEED)
    print(f"excluding {len(exclude)} calibration images from training", flush=True)

    items = []
    for sample in load_samples(spec, per_class * 2, seed=1, exclude_keys=exclude):
        rgb = Image.fromarray(sample.image_bgr[:, :, ::-1])
        items.append((rgb.resize((STORE_SIZE, STORE_SIZE), Image.BILINEAR), sample.label))
    random.Random(1).shuffle(items)
    return items


def _auc(scores: list[float], labels: list[int]) -> float:
    from sklearn.metrics import roc_auc_score

    return float(roc_auc_score(labels, scores))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--per-class", type=int, default=3000)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--seed", type=int, default=0, help="training seed; the sampled image pool is fixed")
    parser.add_argument("--no-augment", action="store_true", help="ablation: disable flip/rescale/JPEG augmentation")
    args = parser.parse_args()
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    settings = get_settings()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu":
        raise SystemExit("No GPU found. Run this on a Colab/Kaggle GPU runtime.")

    processor = AutoImageProcessor.from_pretrained(
        settings.spatial_model_id, revision=settings.spatial_model_revision
    )
    model = AutoModelForImageClassification.from_pretrained(
        settings.spatial_model_id, revision=settings.spatial_model_revision
    ).to(device)

    id2label = {int(k): str(v) for k, v in model.config.id2label.items()}
    if len(id2label) != 2:
        raise SystemExit(f"expected a binary classifier, got labels {id2label!r}")
    positive = _resolve_positive_index(id2label)
    negative = next(i for i in id2label if i != positive)

    pool = _load_pool(args.per_class)
    cut = int(len(pool) * 0.9)
    train_items, val_items = pool[:cut], pool[cut:]
    print(f"train={len(train_items)} val={len(val_items)}", flush=True)

    train_loader = DataLoader(
        _Faces(train_items, processor, positive, negative, augment=not args.no_augment, seed=args.seed),
        batch_size=args.batch_size, shuffle=True, num_workers=2,
    )
    val_loader = DataLoader(
        _Faces(val_items, processor, positive, negative, augment=False),
        batch_size=args.batch_size, num_workers=2,
    )

    optimiser = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    scaler = torch.cuda.amp.GradScaler()
    best_auc, best_state = -1.0, None

    for epoch in range(args.epochs):
        model.train()
        for pixels, target in train_loader:
            pixels, target = pixels.to(device), target.to(device)
            with torch.autocast("cuda", dtype=torch.float16):
                loss = torch.nn.functional.cross_entropy(model(pixel_values=pixels).logits, target)
            optimiser.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(optimiser)
            scaler.update()

        model.eval()
        scores: list[float] = []
        labels: list[int] = []
        with torch.no_grad():
            for pixels, target in val_loader:
                probs = model(pixel_values=pixels.to(device)).logits.softmax(-1)[:, positive]
                scores.extend(probs.cpu().tolist())
                labels.extend((target == positive).int().tolist())
        auc = _auc(scores, labels)
        print(f"epoch {epoch + 1}: in-distribution val AUC {auc:.4f}", flush=True)
        if auc > best_auc:
            best_auc = auc
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

    model.load_state_dict(best_state)
    args.out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.out)
    processor.save_pretrained(args.out)
    print(f"saved best checkpoint (val AUC {best_auc:.4f}) to {args.out}", flush=True)
    print(
        "NOTE: that AUC is in-distribution. The cross-dataset number only exists "
        "after `python -m eval.run` on df40faces.",
        flush=True,
    )


if __name__ == "__main__":
    main()
