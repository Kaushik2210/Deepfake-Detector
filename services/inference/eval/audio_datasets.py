"""Audio evaluation dataset loaders.

The two corpora turned out to need genuinely different loading strategies,
discovered only by trying each and hitting its actual shape:

- **ASVspoof2019 LA** (`Bisher/ASVspoof_2019_LA`) is a proper Hugging Face
  `datasets` repo with row-group-chunked parquet, so it streams cleanly through
  `datasets.load_dataset(..., streaming=True)`.
- **ASVspoof2021 DF** (`Bisher/ASVspoof_2021_DF`) stores its payload as one
  36.7 GB ZIP with a custom loading script. `streaming=True` cannot avoid
  downloading the whole archive for a repo shaped that way -- confirmed by
  running it and watching it stall silently for many minutes with no progress.
  This is read the same way datasets.py already reads the *image* corpora's
  ZIPs: `HfFileSystem` gives a seekable handle over ranged HTTP, so `zipfile`
  can read the central directory and pull out individual members (each tens of
  KB) without ever fetching the archive as a whole.

Both are decoded through this project's own `audio_io.decode_audio`
(soundfile-based) rather than `datasets`'s default Audio decoder, which
requires `torchcodec`, which itself requires a system FFmpeg install this
project deliberately avoids for the shipped service -- see DECISIONS.md.

Licences verified against the primary source (Zenodo's own record metadata, not
a page summary) before this was written -- see LICENSES.md and DECISIONS.md for
two cases where an earlier guess (a license, then a dataset repo ID) was wrong.
"""

from __future__ import annotations

import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

import numpy as np

Label = Literal[0, 1]  # 0 = bonafide, 1 = spoof

_SPOOF_HINTS = ("spoof", "fake", "synthetic", "deepfake")
_BONAFIDE_HINTS = ("bonafide", "real", "genuine", "authentic")


@dataclass(frozen=True)
class AudioDatasetSpec:
    key: str
    licence: str
    commercial_use: bool
    description: str
    hf_id: str


AUDIO_DATASETS: dict[str, AudioDatasetSpec] = {
    "asvspoof2019": AudioDatasetSpec(
        key="asvspoof2019",
        hf_id="Bisher/ASVspoof_2019_LA",
        licence="ODC-By",
        commercial_use=True,
        description=(
            "ASVspoof2019 LA evaluation partition -- the same corpus AASIST was "
            "trained on. Used to fit calibration; measures in-distribution "
            "performance, not generalisation."
        ),
    ),
    "asvspoof2021": AudioDatasetSpec(
        key="asvspoof2021",
        hf_id="Bisher/ASVspoof_2021_DF",
        licence="ODC-By",
        commercial_use=True,
        description=(
            "ASVspoof2021 DF (speech deepfake track) evaluation partition -- "
            "different attack algorithms and lossy-codec conditions than 2019. "
            "Held out entirely for reporting."
        ),
    ),
}


@dataclass
class AudioSample:
    waveform: np.ndarray
    sample_rate: int
    label: Label
    dataset: str
    key: str


def _resolve_spoof_index(names: list[str]) -> int:
    """Which ClassLabel index means "spoof", from the label names themselves.

    Mirrors registry.py's _resolve_positive_index: getting this backwards would
    silently invert every label in the split, which corrupts every metric
    downstream without looking wrong at a glance.
    """
    lowered = {i: name.lower() for i, name in enumerate(names)}

    spoof = {i for i, name in lowered.items() if any(h in name for h in _SPOOF_HINTS)}
    bonafide = {i for i, name in lowered.items() if any(h in name for h in _BONAFIDE_HINTS)}
    spoof -= bonafide

    if len(spoof) == 1:
        return spoof.pop()
    if len(names) == 2 and len(bonafide) == 1 and not spoof:
        return next(i for i in lowered if i not in bonafide)

    raise ValueError(
        f"could not identify the spoof-class index from ClassLabel names {names!r}; "
        "refusing to guess, because guessing wrong inverts every label"
    )


def _load_asvspoof2019(spec: AudioDatasetSpec, limit: int, seed: int) -> Iterator[AudioSample]:
    """Bisher/ASVspoof_2019_LA: parquet-chunked, streams via `datasets`."""
    from datasets import load_dataset

    from app.pipeline.audio_io import decode_audio

    label_column = "key"  # this repo's ClassLabel column; "label" on the 2021 repo
    stream = load_dataset(spec.hf_id, split="test", streaming=True)
    spoof_index = _resolve_spoof_index(stream.features[label_column].names)
    # .cast_column("audio", Audio(decode=False)) does not reliably disable
    # decoding on a streaming IterableDataset in datasets 5.x -- it still routed
    # through the torchcodec-backed decoder. .decode(False) is the version that
    # actually works, confirmed by running this against the real dataset.
    stream = stream.decode(False)
    # A shuffle buffer must fill completely before the first row is yielded, so
    # this is sized against `limit` rather than a large fixed constant -- a
    # 10,000-row buffer to draw a 40-sample smoke test made the harness stall
    # for minutes doing nothing observable before it moved a single frame.
    stream = stream.shuffle(seed=seed, buffer_size=max(200, limit * 10))

    per_class = limit // 2
    emitted = {0: 0, 1: 0}

    for index, row in enumerate(stream):
        if emitted[0] >= per_class and emitted[1] >= per_class:
            break

        label: Label = 1 if int(row[label_column]) == spoof_index else 0
        if emitted[label] >= per_class:
            continue

        raw_bytes = row["audio"]["bytes"]
        if not raw_bytes:
            continue
        try:
            waveform, sample_rate = decode_audio(raw_bytes)
        except Exception:
            continue

        emitted[label] += 1
        row_key = row.get("audio_file_name") or row.get("path")
        yield AudioSample(
            waveform=waveform,
            sample_rate=sample_rate,
            label=label,
            dataset=spec.key,
            key=str(row_key) if row_key else f"{spec.key}::{index}",
        )


# Path shape inside ASVspoof_DF_2021.zip: content/DF/{split}/{label}/{file}.flac
_ZIP_ENTRY = "datasets/Bisher/ASVspoof_2021_DF/ASVspoof_DF_2021.zip"
_ZIP_SPLIT_SEGMENT = 2
_ZIP_LABEL_SEGMENT = 3
_ZIP_TARGET_SPLIT = "test"
_ZIP_LABEL_NAMES: dict[str, Label] = {"real": 0, "fake": 1}


def _load_asvspoof2021(spec: AudioDatasetSpec, limit: int, seed: int) -> Iterator[AudioSample]:
    """Bisher/ASVspoof_2021_DF: one 36.7 GB ZIP, read the same way datasets.py
    reads the image corpora's ZIPs -- central directory + individual ranged
    member reads via HfFileSystem, never the whole archive."""
    import random

    from huggingface_hub import HfFileSystem

    from app.pipeline.audio_io import decode_audio

    fs = HfFileSystem()
    rng = random.Random(seed)
    per_class = limit // 2
    emitted = {0: 0, 1: 0}

    with fs.open(_ZIP_ENTRY, "rb") as handle:
        with zipfile.ZipFile(handle) as archive:
            # Every matching candidate is kept here, not just the first `per_class`
            # seen per label: capping the plan before any decode is attempted means
            # a decode failure permanently loses that slot, since nothing backfills
            # it. That silently under-delivered before -- a `--limit 60` request
            # returned 31 scored samples with no error, because 29 of the 60
            # candidates picked before decoding happened to fail to decode. Trying
            # every shuffled candidate in order (stopping once both class quotas
            # are actually met) lets later candidates backfill earlier failures,
            # the same way the streaming 2019 loader naturally does.
            plan: list[tuple[str, Label]] = []
            for name in archive.namelist():
                if name.endswith("/") or not name.lower().endswith(".flac"):
                    continue
                parts = name.split("/")
                if len(parts) <= max(_ZIP_SPLIT_SEGMENT, _ZIP_LABEL_SEGMENT):
                    continue
                if parts[_ZIP_SPLIT_SEGMENT] != _ZIP_TARGET_SPLIT:
                    continue
                label = _ZIP_LABEL_NAMES.get(parts[_ZIP_LABEL_SEGMENT])
                if label is not None:
                    plan.append((name, label))

            rng.shuffle(plan)

            for name, label in plan:
                if emitted[0] >= per_class and emitted[1] >= per_class:
                    break
                if emitted[label] >= per_class:
                    continue
                try:
                    raw_bytes = archive.read(name)
                except Exception:
                    continue
                try:
                    waveform, sample_rate = decode_audio(raw_bytes)
                except Exception:
                    continue

                emitted[label] += 1
                yield AudioSample(
                    waveform=waveform,
                    sample_rate=sample_rate,
                    label=label,
                    dataset=spec.key,
                    key=name,
                )


_LOADERS = {
    "asvspoof2019": _load_asvspoof2019,
    "asvspoof2021": _load_asvspoof2021,
}


def load_audio_samples(
    spec: AudioDatasetSpec, limit: int, seed: int = 0
) -> Iterator[AudioSample]:
    """Yield up to `limit` samples, balanced across bonafide/spoof."""
    return _LOADERS[spec.key](spec, limit, seed)
