"use client";

import { FormEvent, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  uploadClip,
  type ClipType,
  type SourceType,
} from "@/lib/api";

export function ClipUploadForm() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [sourceType, setSourceType] = useState<SourceType>("individual");
  const [clipType, setClipType] = useState<ClipType>("shot");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!file) {
      setError("Choose a clip to upload");
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
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-zinc-800">Clip file</span>
          <input
            ref={fileInputRef}
            type="file"
            accept="video/mp4,video/quicktime,.mp4,.mov"
            required
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="text-sm text-zinc-700 file:mr-3 file:rounded-md file:border-0 file:bg-zinc-100 file:px-3 file:py-2 file:text-sm file:font-medium file:text-zinc-800 hover:file:bg-zinc-200"
          />
        </label>
        <p className="mt-1 text-xs text-zinc-500">mp4 or mov, max ~25 seconds, 50MB</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-zinc-800">Source</span>
          <select
            value={sourceType}
            onChange={(e) => setSourceType(e.target.value as SourceType)}
            className="rounded-md border border-zinc-300 bg-white px-3 py-2 outline-none ring-orange-600 focus:ring-2"
          >
            <option value="individual">Individual drill (solo)</option>
            <option value="gameplay">Gameplay (multi-player)</option>
          </select>
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-zinc-800">Clip type</span>
          <select
            value={clipType}
            onChange={(e) => setClipType(e.target.value as ClipType)}
            className="rounded-md border border-zinc-300 bg-white px-3 py-2 outline-none ring-orange-600 focus:ring-2"
          >
            <option value="shot">Shot</option>
            <option value="pass">Pass</option>
            <option value="drive">Drive</option>
          </select>
        </label>
      </div>

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
        className="rounded-md bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-60"
      >
        {loading ? "Uploading…" : "Upload clip"}
      </button>
    </form>
  );
}
