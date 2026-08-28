"use client";

import { useRouter } from "next/navigation";
import { useId, useRef, useState } from "react";
import { FileAudio, FileVideo, ImageIcon, UploadCloud } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { cn } from "@/lib/utils";

const ACCEPTED_IMAGE = ["image/jpeg", "image/png", "image/webp", "image/bmp"];
const ACCEPTED_VIDEO = ["video/mp4", "video/quicktime", "video/webm", "video/x-matroska"];
const ACCEPTED_AUDIO = [
  "audio/wav",
  "audio/x-wav",
  "audio/flac",
  "audio/x-flac",
  "audio/ogg",
  "audio/mpeg",
];
const ACCEPTED = [...ACCEPTED_IMAGE, ...ACCEPTED_VIDEO, ...ACCEPTED_AUDIO];

function mediaKindLabel(type: string): "video" | "audio" | "image" {
  if (ACCEPTED_VIDEO.includes(type)) return "video";
  if (ACCEPTED_AUDIO.includes(type)) return "audio";
  return "image";
}

function MediaKindIcon({ type }: { type: string }) {
  const kind = mediaKindLabel(type);
  const props = { className: "size-6 text-muted-foreground", "aria-hidden": true as const };
  if (kind === "video") return <FileVideo {...props} />;
  if (kind === "audio") return <FileAudio {...props} />;
  return <ImageIcon {...props} />;
}

export function UploadForm({ ttlHours }: { ttlHours: number }) {
  const router = useRouter();
  const inputId = useId();
  const consentId = useId();
  const inputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [consented, setConsented] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [dragActive, setDragActive] = useState(false);

  function chooseFile(next: File | null) {
    if (next && !ACCEPTED.includes(next.type)) {
      setError(`Unsupported file type: ${next.type || "unknown"}`);
      setFile(null);
      return;
    }
    setFile(next);
    setError(null);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!file || !consented) return;

    setSubmitting(true);
    setError(null);

    const form = new FormData();
    form.append("file", file);
    form.append("consent", "true");

    try {
      const response = await fetch("/api/analyze", { method: "POST", body: form });
      const body = await response.json();

      if (!response.ok) {
        setError(body.error ?? "upload failed");
        setSubmitting(false);
        return;
      }

      router.push(`/report/${body.job_id}`);
    } catch {
      setError("could not reach the server");
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <div>
        <label
          htmlFor={inputId}
          onDragOver={(event) => {
            event.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragActive(false);
            chooseFile(event.dataTransfer.files?.[0] ?? null);
          }}
          className={cn(
            "flex cursor-pointer flex-col items-center gap-3 rounded-xl border-2 border-dashed bg-card px-8 py-10 text-center transition-colors",
            dragActive ? "border-primary bg-accent" : "border-border hover:border-muted-foreground/50",
          )}
        >
          {file ? (
            <>
              <MediaKindIcon type={file.type} />
              <div>
                <p className="font-medium">{file.name}</p>
                <p className="text-xs text-muted-foreground">
                  {(file.size / 1024).toFixed(0)} KB · {file.type}
                </p>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={(event) => {
                  event.preventDefault();
                  chooseFile(null);
                  if (inputRef.current) inputRef.current.value = "";
                }}
              >
                Choose a different file
              </Button>
            </>
          ) : (
            <>
              <UploadCloud className="size-8 text-muted-foreground" aria-hidden="true" />
              <div>
                <p className="font-medium">
                  Drag and drop a file, or{" "}
                  <span className="text-primary underline underline-offset-4">browse</span>
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Image: JPEG, PNG, WebP, or BMP · Video: MP4, MOV, WebM, or MKV, up to 60
                  seconds and 100&nbsp;MB · Audio: WAV, FLAC, OGG, or MP3, up to 5 minutes and
                  25&nbsp;MB
                </p>
              </div>
            </>
          )}
        </label>
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept={ACCEPTED.join(",")}
          className="sr-only"
          onChange={(event) => chooseFile(event.target.files?.[0] ?? null)}
        />
      </div>

      {/*
        Privacy principle 4: upload is an explicit, per-item action. The consent
        box is unchecked by default, resets with each file, and the submit button
        stays disabled until it is ticked — nothing leaves the browser before then.
      */}
      <div className="flex items-start gap-3 rounded-lg border bg-card p-4">
        <Checkbox
          id={consentId}
          checked={consented}
          onCheckedChange={(checked) => setConsented(checked === true)}
          className="mt-0.5"
        />
        <Label htmlFor={consentId} className="cursor-pointer font-normal leading-relaxed">
          I understand this file will be uploaded to VeriFrame&rsquo;s servers for analysis
          and automatically deleted after {ttlHours} hours. I can delete it sooner from the
          report page.
        </Label>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Button type="submit" disabled={!file || !consented || submitting} size="lg" className="w-full">
        {submitting ? "Uploading…" : `Analyse this ${file ? mediaKindLabel(file.type) : "file"}`}
      </Button>
    </form>
  );
}
