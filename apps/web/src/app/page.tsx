import Link from "next/link";

import { UploadForm } from "@/components/UploadForm";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function HomePage() {
  const ttlHours = Number(process.env.MEDIA_TTL_HOURS ?? 24);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Analyse an image, video, or audio clip
        </h1>
        <p className="mt-2 max-w-2xl text-muted-foreground">
          VeriFrame estimates how likely media is to have been manipulated and shows
          you the evidence behind that estimate. It does not return a verdict, and
          results are a signal for human review rather than proof.
        </p>
      </div>

      <UploadForm ttlHours={ttlHours} />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">What this tool cannot do</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
            <li>
              It cannot tell you who created a piece of media or who appears in it.
              There is no face recognition or identity matching.
            </li>
            <li>
              It cannot prove media is genuine or fabricated. Detectors degrade
              sharply on media unlike what they were validated on, and the report
              says so when that applies.
            </li>
            <li>
              Every accuracy figure it does show traces to a real, cross-dataset
              evaluation run — see the{" "}
              <Link href="/accuracy" className="text-primary underline underline-offset-4">
                accuracy page
              </Link>{" "}
              for the numbers and their caveats, not a marketing claim.
            </li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
