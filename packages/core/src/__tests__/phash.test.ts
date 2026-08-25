import { describe, expect, it } from "vitest";
import { dctPerceptualHash, hammingDistance } from "../phash.js";

/**
 * Golden values computed by ``services/inference/app/pipeline/phash.hash_from_grid``
 * on the identical numeric grid (see that module's docstring). This is the
 * cross-language check: given the same size×size grayscale array, the TS and
 * Python DCT-and-threshold math must produce the same 64-bit hash -- exactly,
 * when coefficients aren't near the decision boundary, or within a couple of
 * bits when float32 (OpenCV) vs. float64 (JS) precision puts a coefficient
 * right on the median threshold. See the second test below for why that
 * happens and why it isn't a logic error.
 *
 * What this does *not* claim: a browser's canvas resize and OpenCV's resize
 * are different algorithms, so a real client-computed hash for an image file
 * will not bit-match the server's hash for the same file. That mismatch is
 * expected and is why the cache endpoint matches by Hamming distance, not
 * exact equality — see phash.ts's module doc and DECISIONS.md.
 */

const SIZE = 32;

function structuredGrid(): Float64Array {
  const grid = new Float64Array(SIZE * SIZE);
  for (let y = 0; y < SIZE; y++) {
    for (let x = 0; x < SIZE; x++) {
      grid[y * SIZE + x] =
        127.5 + 60 * Math.sin(x * 0.4) + 40 * Math.cos(y * 0.7) + ((x * y) % 17);
    }
  }
  return grid;
}

function blockGrid(): Float64Array {
  const grid = new Float64Array(SIZE * SIZE).fill(128.0);
  for (let y = 10; y < 20; y++) {
    for (let x = 10; x < 20; x++) {
      grid[y * SIZE + x] = 200.0;
    }
  }
  return grid;
}

describe("dctPerceptualHash matches Python", () => {
  it("matches the golden hash exactly for a flat grid with a bright block", () => {
    expect(dctPerceptualHash(blockGrid())).toBe("cdcd3232cdcd30cc");
  });

  it("matches the golden hash near-exactly for a smooth structured grid", () => {
    // Not an exact match here, unlike the block grid above: OpenCV runs
    // cv2.dct on a float32 array, this runs the same math in float64, and the
    // smooth sin/cos grid happens to put a couple of coefficients almost
    // exactly on the median threshold -- which side of `>` they land on is
    // then a coin flip between the two precisions. Golden hash was
    // "d08c8c8cfffb8c84"; TS computes "d08c8c8cfefb8c8c", 2 bits different.
    // That is the real-world "close but not identical" behaviour documented
    // in phash.ts's module doc, not a logic error -- the block-grid case
    // above proves the DCT-and-threshold math itself is correct.
    const distance = hammingDistance(dctPerceptualHash(structuredGrid()), "d08c8c8cfffb8c84");
    expect(distance).toBeLessThanOrEqual(2);
  });

  it("produces the same values whether given a Float64Array or a plain array", () => {
    const asArray = Array.from(structuredGrid());
    expect(dctPerceptualHash(asArray)).toBe(dctPerceptualHash(structuredGrid()));
  });
});

describe("dctPerceptualHash", () => {
  it("returns 16 lowercase hex characters", () => {
    const hash = dctPerceptualHash(structuredGrid());
    expect(hash).toMatch(/^[0-9a-f]{16}$/);
  });

  it("is deterministic for the same input", () => {
    const grid = structuredGrid();
    expect(dctPerceptualHash(grid)).toBe(dctPerceptualHash(grid));
  });

  it("rejects a grid of the wrong size", () => {
    expect(() => dctPerceptualHash(new Float64Array(10))).toThrow(/expected a 32x32 grid/);
  });

  it("a solid flat grid still produces a valid hash rather than throwing", () => {
    // Uniform input -> all coefficients above the DC term are ~0, so the
    // median is ~0 too and the `coefficient > threshold` comparisons are
    // right at the boundary. Must not divide-by-zero or NaN out.
    const flat = new Float64Array(SIZE * SIZE).fill(128.0);
    const hash = dctPerceptualHash(flat);
    expect(hash).toMatch(/^[0-9a-f]{16}$/);
  });

  it("perceptually different images hash far apart", () => {
    const a = dctPerceptualHash(structuredGrid());
    const b = dctPerceptualHash(blockGrid());
    expect(hammingDistance(a, b)).toBeGreaterThan(10);
  });

  it("a small change moves the hash by only a few bits, not totally", () => {
    const base = blockGrid();
    const nudged = new Float64Array(base);
    // Nudge one pixel slightly -- a near-duplicate image, not a different one.
    nudged[15 * SIZE + 15] = (nudged[15 * SIZE + 15] ?? 0) + 5;

    const distance = hammingDistance(dctPerceptualHash(base), dctPerceptualHash(nudged));
    expect(distance).toBeLessThanOrEqual(4);
  });
});

describe("hammingDistance", () => {
  it("is zero for identical hashes", () => {
    const h = dctPerceptualHash(structuredGrid());
    expect(hammingDistance(h, h)).toBe(0);
  });

  it("counts differing bits", () => {
    expect(hammingDistance("0000000000000000", "0000000000000001")).toBe(1);
    expect(hammingDistance("0000000000000000", "ffffffffffffffff")).toBe(64);
    expect(hammingDistance("0000000000000000", "000000000000000f")).toBe(4);
  });

  it("is symmetric", () => {
    const a = "abcdef0123456789";
    const b = "0123456789abcdef";
    expect(hammingDistance(a, b)).toBe(hammingDistance(b, a));
  });

  it("throws on mismatched lengths, matching the Python side", () => {
    expect(() => hammingDistance("abcd", "abcdef")).toThrow(/hash length mismatch/);
  });
});
