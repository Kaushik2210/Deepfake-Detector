"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

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

export function UploadForm({ ttlHours }: { ttlHours: number }) {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [consented, setConsented] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

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
          htmlFor="file"
          className="block cursor-pointer rounded-lg border-2 border-dashed border-slate-300 bg-white p-8 text-center hover:border-slate-400"
        >
          <span className="text-sm text-slate-600">
            {file ? (
              <>
                <strong className="text-slate-900">{file.name}</strong>
                <br />
                {(file.size / 1024).toFixed(0)} KB · {file.type}
              </>
            ) : (
              <>
                Choose an image, a short video, or an audio clip
                <br />
                <span className="text-xs text-slate-500">
                  Image: JPEG, PNG, WebP, or BMP · Video: MP4, MOV, WebM, or MKV,
                  up to 60 seconds and 100 MB · Audio: WAV, FLAC, OGG, or MP3, up
                  to 5 minutes and 25 MB
                </span>
              </>
            )}
          </span>
        </label>
        <input
          id="file"
          type="file"
          accept={ACCEPTED.join(",")}
          className="sr-only"
          onChange={(event) => {
            setFile(event.target.files?.[0] ?? null);
            setError(null);
          }}
        />
      </div>

      {/*
        Privacy principle 4: upload is an explicit, per-item action. The consent
        box is unchecked by default, resets with each file, and the submit button
        stays disabled until it is ticked — nothing leaves the browser before then.
      */}
      <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-slate-200 bg-white p-4">
        <input
          type="checkbox"
          checked={consented}
          onChange={(event) => setConsented(event.target.checked)}
          className="mt-1"
        />
        <span className="text-sm text-slate-700">
          I understand this file will be uploaded to VeriFrame&rsquo;s servers for
          analysis and automatically deleted after {ttlHours} hours. I can delete it
          sooner from the report page.
        </span>
      </label>

      {error && (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={!file || !consented || submitting}
        className="rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        {submitting
          ? "Uploading…"
          : `Analyse this ${file ? mediaKindLabel(file.type) : "image"}`}
      </button>
    </form>
  );
}
