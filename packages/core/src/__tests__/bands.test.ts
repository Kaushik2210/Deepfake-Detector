import { describe, expect, it } from "vitest";
import { scoreToBand, BAND_DEFINITIONS } from "../bands.js";

describe("scoreToBand", () => {
  it("maps midpoints of each band to the expected id", () => {
    expect(scoreToBand(0.1).id).toBe("low");
    expect(scoreToBand(0.3).id).toBe("weak");
    expect(scoreToBand(0.5).id).toBe("mixed");
    expect(scoreToBand(0.8).id).toBe("strong");
    expect(scoreToBand(0.95).id).toBe("very_strong");
  });

  it("treats lower boundaries as inclusive, pushing exact boundary scores into the higher band", () => {
    expect(scoreToBand(0.2).id).toBe("weak");
    expect(scoreToBand(0.45).id).toBe("mixed");
    expect(scoreToBand(0.7).id).toBe("strong");
    expect(scoreToBand(0.88).id).toBe("very_strong");
  });

  it("handles the extremes of [0, 1]", () => {
    expect(scoreToBand(0).id).toBe("low");
    expect(scoreToBand(1).id).toBe("very_strong");
  });

  it("rejects out-of-range or non-finite scores", () => {
    expect(() => scoreToBand(-0.01)).toThrow(RangeError);
    expect(() => scoreToBand(1.01)).toThrow(RangeError);
    expect(() => scoreToBand(NaN)).toThrow(RangeError);
  });

  it("band definitions cover [0, 1] with no gaps", () => {
    const sorted = [...BAND_DEFINITIONS].sort((a, b) => a.min - b.min);
    expect(sorted[0]?.min).toBe(0);
    expect(sorted[sorted.length - 1]?.max).toBe(1);
    for (let i = 1; i < sorted.length; i++) {
      expect(sorted[i]?.min).toBe(sorted[i - 1]?.max);
    }
  });
});
