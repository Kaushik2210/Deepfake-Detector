/**
 * Perceptual hash (pHash), ported to match ``services/inference/app/pipeline/phash.py``.
 *
 * The DCT-and-threshold math below is verified to match the Python side
 * exactly (see the cross-language test) — feed both the same size×size
 * grayscale grid and they produce the identical 64-bit hash.
 *
 * What is *not* guaranteed to match: the browser's `<canvas>` resize and
 * OpenCV's `INTER_AREA` are different algorithms, so a client-computed hash
 * for a file and the server's hash for a re-upload of the identical bytes
 * will usually land close but not bit-identical. That is why
 * `POST /v1/analyze/hash` matches by Hamming distance rather than requiring
 * an exact hash — see LICENSES.md / DECISIONS.md for the reasoning.
 */

const DCT_SIZE = 32;
const HASH_SIZE = 8;

let cachedBasis: { size: number; matrix: Float64Array } | null = null;

/** The size×size orthonormal DCT-II basis, memoised since it never changes. */
function dctBasis(size: number): Float64Array {
  if (cachedBasis && cachedBasis.size === size) return cachedBasis.matrix;

  const matrix = new Float64Array(size * size);
  for (let k = 0; k < size; k++) {
    const alpha = k === 0 ? Math.sqrt(1 / size) : Math.sqrt(2 / size);
    for (let x = 0; x < size; x++) {
      matrix[k * size + x] = alpha * Math.cos((Math.PI / size) * (x + 0.5) * k);
    }
  }

  cachedBasis = { size, matrix };
  return matrix;
}

/**
 * Separable 2D orthonormal DCT-II — row transform, then column transform —
 * matching `cv2.dct` on a 2D array to floating-point precision.
 */
function dct2d(pixels: Float64Array, size: number): Float64Array {
  const basis = dctBasis(size);
  const rows = new Float64Array(size * size);

  // Non-null throughout this function: every loop index is bounded by `size`
  // against arrays of length size*size, so all accesses are in range.
  for (let y = 0; y < size; y++) {
    for (let k = 0; k < size; k++) {
      let sum = 0;
      for (let x = 0; x < size; x++) {
        sum += pixels[y * size + x]! * basis[k * size + x]!;
      }
      rows[y * size + k] = sum;
    }
  }

  const out = new Float64Array(size * size);
  for (let k2 = 0; k2 < size; k2++) {
    for (let k = 0; k < size; k++) {
      let sum = 0;
      for (let y = 0; y < size; y++) {
        sum += rows[y * size + k]! * basis[k2 * size + y]!;
      }
      out[k2 * size + k] = sum;
    }
  }

  return out;
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  // Non-null: mid (and mid-1, when reached) are always valid indices into a
  // non-empty sorted array -- callers never pass an empty coefficient list.
  return sorted.length % 2 === 0
    ? (sorted[mid - 1]! + sorted[mid]!) / 2
    : sorted[mid]!;
}

/**
 * Given a `size`×`size` grayscale pixel grid (row-major, values 0-255),
 * compute the 64-bit hash as 16 lowercase hex characters.
 *
 * Pure and DOM-free on purpose: this is the part that must match Python
 * exactly and is unit-tested against it directly, decoupled from the
 * unavoidable resize-algorithm mismatch a browser adapter introduces.
 */
export function dctPerceptualHash(pixels: Float64Array | number[], size = DCT_SIZE): string {
  if (pixels.length !== size * size) {
    throw new Error(`expected a ${size}x${size} grid (${size * size} values), got ${pixels.length}`);
  }

  const grid = pixels instanceof Float64Array ? pixels : Float64Array.from(pixels);
  const dct = dct2d(grid, size);

  const coefficients: number[] = [];
  for (let y = 0; y < HASH_SIZE; y++) {
    for (let x = 0; x < HASH_SIZE; x++) {
      // Non-null: y,x < HASH_SIZE <= size, so this is always in bounds.
      coefficients.push(dct[y * size + x]!);
    }
  }

  // Exclude the DC term (index 0) from the median: it carries overall
  // brightness, not structure -- matching phash.py's `coefficients[1:]`.
  const threshold = median(coefficients.slice(1));

  let value = 0n;
  for (const coefficient of coefficients) {
    value = (value << 1n) | (coefficient > threshold ? 1n : 0n);
  }

  return value.toString(16).padStart(16, "0");
}

/** Bit distance between two pHashes; smaller means more perceptually similar. */
export function hammingDistance(a: string, b: string): number {
  if (a.length !== b.length) {
    throw new Error(`hash length mismatch: ${a.length} vs ${b.length}`);
  }

  let x = BigInt(`0x${a}`) ^ BigInt(`0x${b}`);
  let count = 0;
  while (x > 0n) {
    count += Number(x & 1n);
    x >>= 1n;
  }
  return count;
}

/**
 * Draws an image/video/canvas source down to a `DCT_SIZE`×`DCT_SIZE`
 * grayscale grid using the given 2D canvas context, ready for
 * `dctPerceptualHash`.
 *
 * Browser-only (needs a real `CanvasRenderingContext2D`), so it is not unit
 * tested here — `dctPerceptualHash` above carries the math correctness
 * guarantee, and this adapter is exercised by manual testing of the built
 * extension. Luma weights (0.299/0.587/0.114) match OpenCV's default
 * `COLOR_BGR2GRAY` (ITU-R BT.601), for the closest practical agreement with
 * the server's hash on the same image.
 */
export function grayscaleGridFromCanvas(
  ctx: CanvasRenderingContext2D,
  source: CanvasImageSource,
  size: number = DCT_SIZE,
): Float64Array {
  ctx.clearRect(0, 0, size, size);
  ctx.drawImage(source, 0, 0, size, size);

  const { data } = ctx.getImageData(0, 0, size, size);
  const grid = new Float64Array(size * size);

  for (let i = 0; i < size * size; i++) {
    // Non-null: i*4+2 < data.length by construction (4 channels x size x size).
    const r = data[i * 4]!;
    const g = data[i * 4 + 1]!;
    const b = data[i * 4 + 2]!;
    grid[i] = 0.299 * r + 0.587 * g + 0.114 * b;
  }

  return grid;
}
