"""Stream D — provenance and metadata.

This is the highest-precision stream when it fires, because it reads
cryptographic and recorded facts rather than inferring from pixels. A valid C2PA
manifest from a signer we trust is stronger evidence than any statistical
detector, which is why fusion gives it an override path rather than merely a
large weight.

It is also the stream that fires least often: most images in circulation carry no
Content Credentials at all, and stripped metadata is the norm on social
platforms. Absence therefore says almost nothing, and this module is careful to
report "unknown" rather than treating missing provenance as suspicious.

On watermarks: Google SynthID is only detectable through Google's own tooling and
there is no public verifier, so we do not claim to check for it. What we do read
is metadata that generators write about themselves, which is trivially removable
and so is treated as a positive signal only, never as exculpatory.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

from PIL import Image

# Substrings that appear in EXIF/XMP when a generator labels its own output.
# Presence is meaningful; absence means nothing, because stripping it is trivial.
_GENERATOR_MARKERS: dict[str, str] = {
    "stable diffusion": "Stable Diffusion",
    "stablediffusion": "Stable Diffusion",
    "midjourney": "Midjourney",
    "dall-e": "DALL·E",
    "dalle": "DALL·E",
    "firefly": "Adobe Firefly",
    "imagen": "Google Imagen",
    "flux": "FLUX",
    "novelai": "NovelAI",
    "invokeai": "InvokeAI",
    "automatic1111": "AUTOMATIC1111",
    "comfyui": "ComfyUI",
}

# Software strings that indicate editing, which is not manipulation in the sense
# this product reports on, but is worth surfacing as context.
_EDITOR_MARKERS = ("photoshop", "gimp", "lightroom", "affinity photo", "pixelmator")


@dataclass
class C2paInfo:
    present: bool
    valid: bool | None = None
    signer: str | None = None
    trusted_signer: bool | None = None
    error: str | None = None


@dataclass
class ProvenanceResult:
    c2pa: C2paInfo
    exif_present: bool
    exif_consistent: bool | None
    generator_marker: str | None
    editor_marker: str | None
    notes: list[str] = field(default_factory=list)

    @property
    def fired(self) -> bool:
        """Whether this stream found anything at all worth reporting."""
        return (
            self.c2pa.present
            or self.generator_marker is not None
            or self.exif_consistent is False
        )


def read_c2pa(raw_bytes: bytes, mime_type: str = "image/jpeg") -> C2paInfo:
    """Read and validate a C2PA manifest, if one is embedded."""
    try:
        import c2pa
    except ImportError:
        return C2paInfo(present=False, error="c2pa library unavailable")

    try:
        with c2pa.Reader(mime_type, io.BytesIO(raw_bytes)) as reader:
            manifest_json = reader.json()
    except Exception as exc:
        message = str(exc)
        # The library raises for "no manifest found", which is the common case
        # and not an error worth surfacing as one.
        if "no claim" in message.lower() or "manifest" in message.lower():
            return C2paInfo(present=False)
        return C2paInfo(present=False, error=message[:200])

    if not manifest_json:
        return C2paInfo(present=False)

    import json

    try:
        manifest = json.loads(manifest_json)
    except json.JSONDecodeError:
        return C2paInfo(present=True, valid=False, error="manifest is not valid JSON")

    active = manifest.get("active_manifest")
    manifests = manifest.get("manifests", {})
    entry = manifests.get(active, {}) if active else {}

    signature = entry.get("signature_info", {})
    signer = signature.get("issuer") or signature.get("common_name")

    # A validation_status array with entries means the manifest failed at least
    # one check. Empty or absent means it validated.
    statuses = manifest.get("validation_status", [])
    valid = len(statuses) == 0

    return C2paInfo(
        present=True,
        valid=valid,
        signer=signer,
        # Trust requires a signer allow-list we do not yet maintain. Reporting
        # None is honest; claiming True would be asserting trust we cannot back.
        trusted_signer=None,
    )


def _exif_text(raw_bytes: bytes) -> tuple[bool, str]:
    """Return (exif present, all textual metadata lowercased)."""
    chunks: list[str] = []
    present = False

    try:
        with Image.open(io.BytesIO(raw_bytes)) as image:
            exif = image.getexif()
            if exif and len(exif) > 0:
                present = True
                for value in exif.values():
                    if isinstance(value, (str, bytes)):
                        chunks.append(
                            value.decode("utf-8", "ignore")
                            if isinstance(value, bytes)
                            else value
                        )

            info = getattr(image, "info", {}) or {}
            for key, value in info.items():
                if isinstance(value, str):
                    chunks.append(f"{key} {value}")
                elif isinstance(value, bytes):
                    chunks.append(value.decode("utf-8", "ignore"))
    except Exception:
        return present, ""

    return present, " ".join(chunks).lower()


def analyze_provenance(raw_bytes: bytes, mime_type: str = "image/jpeg") -> ProvenanceResult:
    c2pa_info = read_c2pa(raw_bytes, mime_type)
    exif_present, text = _exif_text(raw_bytes)

    generator = next(
        (label for marker, label in _GENERATOR_MARKERS.items() if marker in text), None
    )
    editor = next((marker for marker in _EDITOR_MARKERS if marker in text), None)

    notes: list[str] = []

    if c2pa_info.present:
        if c2pa_info.valid:
            signer = c2pa_info.signer or "an unidentified signer"
            notes.append(
                f"This image carries valid Content Credentials (C2PA) signed by {signer}. "
                "Cryptographic provenance is stronger evidence than any statistical "
                "detector, though it describes the signing chain rather than proving "
                "the content was never altered before signing."
            )
        else:
            notes.append(
                "This image carries Content Credentials, but they failed validation. "
                "That can mean the file was altered after signing, or simply that it "
                "was re-encoded in transit."
            )
    else:
        notes.append(
            "No Content Credentials were found. This is the normal case for almost all "
            "images in circulation and is not itself suspicious."
        )

    if generator:
        notes.append(
            f"Metadata names {generator} as the source, which is a strong indication "
            "this image was generated rather than photographed. Note that such metadata "
            "is trivially removed, so its absence elsewhere proves nothing."
        )

    if editor:
        notes.append(
            f"Metadata records editing software ({editor}). Editing is not manipulation "
            "in the sense this report is about, and is extremely common."
        )

    if not exif_present:
        notes.append(
            "The image carries no EXIF metadata. Social platforms strip it routinely, so "
            "this is expected for shared images and carries no weight on its own."
        )

    return ProvenanceResult(
        c2pa=c2pa_info,
        exif_present=exif_present,
        # Contradiction checking across EXIF fields is not implemented, so this
        # stays None rather than defaulting to True and implying we verified it.
        exif_consistent=None,
        generator_marker=generator,
        editor_marker=editor,
        notes=notes,
    )
