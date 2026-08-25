"""Guards the Python schemas against drift from the Zod schemas in packages/core.

These parse the TypeScript source textually rather than executing it. That is
coarse, but it catches the failure that actually bites — a field added on one side
and forgotten on the other — without making the Python suite depend on a Node
toolchain being installed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.schemas import (
    AnalysisReport,
    Conclusion,
    Envelope,
    FaceFinding,
    MediaMeta,
    Provenance,
    StreamResult,
)

_CORE_SCHEMAS = (
    Path(__file__).resolve().parents[3] / "packages" / "core" / "src" / "schemas"
)


def _zod_object_fields(source: str, schema_name: str) -> set[str]:
    """Pull the top-level keys out of a `export const X = z.object({ ... })` block."""
    match = re.search(rf"export const {schema_name} = z\.object\(\{{", source)
    if not match:
        raise AssertionError(f"{schema_name} not found")

    start = match.end()
    depth = 1
    index = start
    while index < len(source) and depth > 0:
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
        index += 1

    body = source[start : index - 1]

    fields: set[str] = set()
    depth = 0
    for line in body.splitlines():
        stripped = line.strip()
        if depth == 0:
            key = re.match(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*:", stripped)
            if key:
                fields.add(key.group(1))
        depth += line.count("{") + line.count("(") - line.count("}") - line.count(")")

    return fields


@pytest.fixture(scope="module")
def report_source() -> str:
    """Concatenates the schema modules, since they were split to avoid a cycle."""
    parts = []
    for name in ("analysis-report.ts", "envelope.ts", "faces.ts"):
        path = _CORE_SCHEMAS / name
        if not path.is_file():
            pytest.skip(f"packages/core not available at {path}")
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


@pytest.mark.parametrize(
    ("schema_name", "model"),
    [
        ("AnalysisReportSchema", AnalysisReport),
        ("StreamResultSchema", StreamResult),
        ("EnvelopeSchema", Envelope),
        ("ProvenanceSchema", Provenance),
        ("MediaMetaSchema", MediaMeta),
        ("FaceFindingSchema", FaceFinding),
        ("ConclusionSchema", Conclusion),
    ],
)
def test_python_and_zod_agree_on_fields(report_source: str, schema_name: str, model) -> None:
    zod_fields = _zod_object_fields(report_source, schema_name)
    python_fields = set(model.model_fields)

    assert python_fields == zod_fields, (
        f"{schema_name} drifted: "
        f"only in Zod {sorted(zod_fields - python_fields)}, "
        f"only in Python {sorted(python_fields - zod_fields)}"
    )


def test_report_requires_the_fields_the_api_contract_promises() -> None:
    promised = {
        "score", "band", "uncertainty", "streams", "envelope", "provenance",
        "media_meta", "model_versions", "processed_at", "ttl_expires_at",
    }
    assert promised <= set(AnalysisReport.model_fields)
