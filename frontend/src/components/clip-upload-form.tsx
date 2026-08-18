"use client";

import { FormEvent, useRef, useState, type DragEvent } from "react";
import { useRouter } from "next/navigation";
import {
  uploadClip,
  type ClipType,
  type SourceType,
} from "@/lib/api";

const CLIP_TYPE_HINTS: Record<ClipType, string> = {
  shot: "Catch-and-shoot or pull-up off the bounce. Form shooting is mechanics only.",
  pass: "Clear pass-like arm release. About 5 usable clips total unlocks a named comparison.",
  drive: "First step toward the rim. About 5 usable clips total unlocks a named comparison.",
};

const TYPES: ClipType[] = ["shot", "pass", "drive"];

export function ClipUploadForm() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [sourceType, setSourceType] = useState<SourceType>("individual");
  const [clipType, setClipType] = useState<ClipType>("shot");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  function takeFile(next: File | null) {
    if (!next) return;
    if (next.size > 50 * 1024 * 1024) {
      setError("File exceeds 50MB limit");
      return;
    }
    setFile(next);
    setError(null);
    setSuccess(null);
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragOver(false);
    takeFile(event.dataTransfer.files?.[0] ?? null);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!file) {
      setError("Choose a clip to upload");
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      setError("File exceeds 50MB limit");
      return;
    }

    setError(null);
    setSuccess(null);
    setLoading(true);
    try {
      const clip = await uploadClip(file, sourceType, clipType);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      setSuccess(`Uploaded ${clip.clip_type} clip (${clip.status.replace("_", " ")})`);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div>
        <p className="text-sm font-medium text-zinc-800">Clip type</p>
        <div className="mt-1.5 grid grid-cols-3 rounded-lg border border-zinc-200 bg-zinc-50 p-0.5">
          {TYPES.map((type) => {
            const selected = clipType === type;
            return (
              <button
                key={type}
                type="button"
                onClick={() => setClipType(type)}
                className={`rounded-md px-2 py-1.5 text-sm font-medium capitalize transition-colors duration-200 ${
                  selected
                    ? "bg-white text-zinc-900 shadow-sm"
                    : "text-zinc-500 hover:text-zinc-800"
                }`}
                aria-pressed={selected}
              >
                {type}
              </button>
            );
          })}
        </div>
        <p className="mt-1.5 text-xs leading-5 text-zinc-500">{CLIP_TYPE_HINTS[clipType]}</p>
      </div>

      <label
        onDragOver={(event) => {
          event.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={`flex min-h-36 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed px-4 py-6 text-center transition-colors duration-200 ${
          dragOver
            ? "border-orange-700 bg-orange-50/60"
            : "border-zinc-300 bg-zinc-50/70 hover:border-zinc-400 hover:bg-zinc-50"
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="video/mp4,video/quicktime,.mp4,.mov"
          required
          onChange={(e) => takeFile(e.target.files?.[0] ?? null)}
          className="sr-only"
        />
        <svg
          viewBox="0 0 24 24"
          className="size-8 text-zinc-400"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          aria-hidden
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M3 15.5V17a3 3 0 0 0 3 3h12a3 3 0 0 0 3-3v-1.5M16 8l-4-4m0 0L8 8m4-4v12"
          />
        </svg>
        <p className="mt-2 text-sm font-medium text-zinc-800">
          {file ? file.name : "Drop a clip here"}
        </p>
        <p className="mt-0.5 text-xs text-zinc-500">
          {file ? `${Math.round(file.size / (1024 * 1024))} MB · mp4 or mov` : "or click to browse · mp4 / mov · 50MB"}
        </p>
      </label>

      <label className="flex flex-col gap-1 text-sm">
        <span className="font-medium text-zinc-800">Source</span>
        <select
          value={sourceType}
          onChange={(e) => setSourceType(e.target.value as SourceType)}
          className="rounded-lg border border-zinc-200 bg-white px-3 py-2.5 text-sm outline-none ring-orange-600 transition-shadow duration-200 focus:ring-2"
        >
          <option value="individual">Individual drill (solo)</option>
          <option value="gameplay">Gameplay (multi-player)</option>
        </select>
      </label>

      {error ? (
        <p className="text-sm text-red-600" role="alert">
          {error}
        </p>
      ) : null}
      {success ? (
        <p className="text-sm text-emerald-700" role="status">
          {success}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={loading}
        className="min-h-10 w-full rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white transition-colors duration-200 hover:bg-zinc-800 disabled:opacity-60"
      >
        {loading ? "Uploading…" : "Upload clip"}
      </button>
    </form>
  );
}
