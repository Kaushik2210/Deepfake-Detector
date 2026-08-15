"""Evaluation dataset loaders.

Neither corpus is published as parquet, so `datasets.load_dataset` streaming is
not available. Both are ZIP archives on the Hugging Face hub, which is served
over HTTP with range support — so `HfFileSystem` gives a seekable handle and
`zipfile` can read the central directory and pull out individual members without
downloading the whole archive. That keeps a 5 GB corpus down to the few hundred
images we actually score.

Nothing is written into the repository; see .gitignore.

Licences are recorded in LICENSES.md. One corpus is non-commercial and is used
for evaluation only — it contributes no weights and no code to the shipped
product, only numbers in a report.
"""

from __future__ import annotations

import io
import random
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from PIL import Image

Label = Literal[0, 1]  # 0 = authentic, 1 = manipulated

_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".bmp", ".webp")


@dataclass(frozen=True)
class ArchiveSource:
    """One ZIP on the hub, and how to read labels out of it."""

    path: str
    label: Label | None = None
    # When label is None, the class is taken from this path segment index.
    label_from_segment: int | None = None
    label_names: dict[str, Label] = field(default_factory=dict)


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    hf_id: str
    licence: str
    commercial_use: bool
    description: str
    sources: tuple[ArchiveSource, ...]


DATASETS: dict[str, DatasetSpec] = {
    "deepfakeface": DatasetSpec(
        key="deepfakeface",
        hf_id="OpenRL/DeepFakeFace",
        licence="Apache-2.0",
        commercial_use=True,
        description=(
            "Real celebrity photographs (IMDB-WIKI) against faces swapped with "
            "InsightFace. Used to fit calibration."
        ),
        sources=(
            ArchiveSource(path="datasets/OpenRL/DeepFakeFace/wiki.zip", label=0),
            ArchiveSource(path="datasets/OpenRL/DeepFakeFace/insight.zip", label=1),
        ),
    ),
    "df40faces": DatasetSpec(
        key="df40faces",
        hf_id="pujanpaudel/deepfake_face_classification",
        licence="CC BY-NC 4.0",
        commercial_use=False,
        description=(
            "Faces whose fakes come from the DF40 test split, covering 40 "
            "manipulation techniques. Held out entirely for reporting."
        ),
        sources=(
            ArchiveSource(
                path="datasets/pujanpaudel/deepfake_face_classification/val.zip",
                label_from_segment=1,
                label_names={"real": 0, "fake": 1},
            ),
        ),
    ),
}


@dataclass
class Sample:
    image_bgr: np.ndarray
    label: Label
    dataset: str
    source: str


def _decode(data: bytes) -> np.ndarray | None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            rgb = np.array(image.convert("RGB"))
    except Exception:
        return None
    if rgb.size == 0:
        return None
    return rgb[:, :, ::-1].copy()


def _entries(archive: zipfile.ZipFile, source: ArchiveSource) -> list[tuple[str, Label]]:
    out: list[tuple[str, Label]] = []

    for name in archive.namelist():
        if name.endswith("/") or not name.lower().endswith(_IMAGE_SUFFIXES):
            continue

        if source.label is not None:
            out.append((name, source.label))
            continue

        parts = name.split("/")
        index = source.label_from_segment
        if index is None or index >= len(parts):
            continue

        label = source.label_names.get(parts[index].lower())
        if label is not None:
            out.append((name, label))

    return out


def load_samples(spec: DatasetSpec, limit: int, seed: int = 0) -> Iterator[Sample]:
    """Yield up to `limit` samples, balanced across the two classes.

    Balance matters: an unbalanced sample would make threshold-based metrics
    reflect the class ratio that happened to be drawn rather than the detector.
    """
    from huggingface_hub import HfFileSystem

    fs = HfFileSystem()
    rng = random.Random(seed)
    per_class = limit // 2
    emitted = {0: 0, 1: 0}

    # Collect candidates first so the shuffle covers the whole archive rather
    # than favouring whichever entries appear early in the central directory.
    plan: list[tuple[str, str, Label]] = []
    for source in spec.sources:
        with fs.open(source.path, "rb") as handle:
            with zipfile.ZipFile(handle) as archive:
                for name, label in _entries(archive, source):
                    plan.append((source.path, name, label))

    rng.shuffle(plan)

    by_archive: dict[str, list[tuple[str, Label]]] = {}
    for archive_path, name, label in plan:
        if emitted[label] >= per_class:
            continue
        emitted[label] += 1
        by_archive.setdefault(archive_path, []).append((name, label))

    for archive_path, wanted in by_archive.items():
        with fs.open(archive_path, "rb") as handle:
            with zipfile.ZipFile(handle) as archive:
                for name, label in wanted:
                    try:
                        data = archive.read(name)
                    except Exception:
                        continue
                    image = _decode(data)
                    if image is None:
                        continue
                    yield Sample(
                        image_bgr=image,
                        label=label,
                        dataset=spec.key,
                        source=archive_path.rsplit("/", 1)[-1],
                    )
