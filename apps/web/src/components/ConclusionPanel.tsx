import type { Conclusion } from "@veriframe/core";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * The plain-language summary, shown first because it is what most readers will
 * actually read. Everything below it on the report is the supporting detail.
 */
export function ConclusionPanel({
  conclusion,
  unit = "face",
}: {
  conclusion: Conclusion;
  /** "frame" for a video's per-frame findings, "face" for an image's faces.
   * Cosmetic only -- the underlying field names describe the same counts
   * either way, a sampled frame's primary face being the unit of analysis.
   * "clip" is accepted for type parity with ReportView's shared `unit` value,
   * but audio reports never have a conclusion, so this component never
   * actually renders with it. */
  unit?: "face" | "frame" | "clip";
}) {
  const { faces_analyzed: analyzed, faces_elevated: elevated } = conclusion;

  return (
    <Card className="border-2 border-foreground/80" size="default">
      <CardHeader>
        <CardTitle className="text-xl">{conclusion.headline}</CardTitle>
        {analyzed > 0 && (
          <p className="text-sm text-muted-foreground">
            {analyzed} {unit}
            {analyzed === 1 ? "" : "s"} analysed
            {elevated > 0 && ` · ${elevated} above the review threshold`}
          </p>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="leading-relaxed">{conclusion.detail}</p>

        <div className="rounded-md border-l-4 border-foreground bg-muted px-4 py-3">
          <p className="text-sm font-medium">What to do next</p>
          <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
            {conclusion.next_steps}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
