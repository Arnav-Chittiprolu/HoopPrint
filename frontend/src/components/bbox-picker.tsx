"use client";

import { useEffect, useRef, useState, type MouseEvent } from "react";
import { getClipFirstFrameUrl, saveClipBbox } from "@/lib/api";

type Rect = { x: number; y: number; w: number; h: number };

export function BboxPicker({
  clipId,
  onSaved,
}: {
  clipId: string;
  onSaved: () => void;
}) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);
  const [rect, setRect] = useState<Rect | null>(null);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        objectUrl = await getClipFirstFrameUrl(clipId);
        if (!cancelled) setSrc(objectUrl);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load first frame");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [clipId]);

  function localPoint(event: MouseEvent<HTMLDivElement>) {
    const img = imgRef.current;
    if (!img) return null;
    const bounds = img.getBoundingClientRect();
    const x = (event.clientX - bounds.left) / bounds.width;
    const y = (event.clientY - bounds.top) / bounds.height;
    return {
      x: Math.min(1, Math.max(0, x)),
      y: Math.min(1, Math.max(0, y)),
    };
  }

  function onPointerDown(event: MouseEvent<HTMLDivElement>) {
    const point = localPoint(event);
    if (!point) return;
    setDragStart(point);
    setRect({ x: point.x, y: point.y, w: 0, h: 0 });
  }

  function onPointerMove(event: MouseEvent<HTMLDivElement>) {
    if (!dragStart) return;
    const point = localPoint(event);
    if (!point) return;
    const x = Math.min(dragStart.x, point.x);
    const y = Math.min(dragStart.y, point.y);
    setRect({
      x,
      y,
      w: Math.abs(point.x - dragStart.x),
      h: Math.abs(point.y - dragStart.y),
    });
  }

  function onPointerUp() {
    setDragStart(null);
  }

  async function onSave() {
    if (!rect || rect.w < 0.03 || rect.h < 0.03) {
      setError("Draw a box around yourself (full body if possible)");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await saveClipBbox(clipId, rect);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save box");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <p className="mt-3 text-xs text-zinc-500">Loading first frame…</p>;
  }
  if (error && !src) {
    return <p className="mt-3 text-xs text-red-600">{error}</p>;
  }
  if (!src) return null;

  return (
    <div className="mt-3 space-y-2">
      <p className="text-xs text-zinc-600">
        Draw a rectangle around <span className="font-medium">you only</span> on the first frame.
      </p>
      <div
        className="relative inline-block max-w-full cursor-crosshair select-none overflow-hidden rounded-lg border border-zinc-200"
        onMouseDown={onPointerDown}
        onMouseMove={onPointerMove}
        onMouseUp={onPointerUp}
        onMouseLeave={onPointerUp}
      >
        <img
          ref={imgRef}
          src={src}
          alt="First frame"
          draggable={false}
          className="block max-h-80 w-full bg-black"
        />
        {rect ? (
          <div
            className="pointer-events-none absolute border-2 border-orange-500 bg-orange-400/20"
            style={{
              left: `${rect.x * 100}%`,
              top: `${rect.y * 100}%`,
              width: `${rect.w * 100}%`,
              height: `${rect.h * 100}%`,
            }}
          />
        ) : null}
      </div>
      {error ? (
        <p className="text-xs text-red-600" role="alert">
          {error}
        </p>
      ) : null}
      <button
        type="button"
        onClick={onSave}
        disabled={saving}
        className="rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-60"
      >
        {saving ? "Saving…" : "Save box and process"}
      </button>
    </div>
  );
}
