"use client";

import { useEffect, useRef, useState, type FormEvent, type PointerEvent } from "react";
import { getClipFrame, saveClipBbox } from "@/lib/api";

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
  const [duration, setDuration] = useState<number | null>(null);
  const [secondInput, setSecondInput] = useState("0");
  const [startS, setStartS] = useState<number | null>(null);
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
        const frame = await getClipFrame(clipId, 0);
        if (cancelled) return;
        objectUrl = frame.url;
        setDuration(frame.durationS);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load clip");
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

  async function onShowSecond(event: FormEvent) {
    event.preventDefault();
    const parsed = Number(secondInput);
    if (!Number.isFinite(parsed) || parsed < 0) {
      setError("Enter a second at or after 0");
      return;
    }
    const clamped = duration != null ? Math.min(parsed, Math.max(0, duration - 0.05)) : parsed;
    setLoading(true);
    setError(null);
    setRect(null);
    try {
      const frame = await getClipFrame(clipId, clamped);
      setSrc((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return frame.url;
      });
      setDuration(frame.durationS);
      setStartS(clamped);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load that second");
    } finally {
      setLoading(false);
    }
  }

  function localPoint(event: PointerEvent<HTMLDivElement>) {
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

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    const point = localPoint(event);
    if (!point) return;
    setDragStart(point);
    setRect({ x: point.x, y: point.y, w: 0, h: 0 });
  }

  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
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

  function onPointerUp(event: PointerEvent<HTMLDivElement>) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    setDragStart(null);
  }

  async function onSave() {
    if (startS == null) {
      setError("Choose a second first");
      return;
    }
    if (!rect || rect.w < 0.03 || rect.h < 0.03) {
      setError("Draw a box around yourself (full body if possible)");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await saveClipBbox(clipId, { ...rect, start_s: startS });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save box");
    } finally {
      setSaving(false);
    }
  }

  const maxHint =
    duration != null && duration > 0 ? `Clip is about ${duration.toFixed(1)} seconds.` : null;

  return (
    <div className="mt-3 space-y-2">
      <form onSubmit={(event) => void onShowSecond(event)} className="space-y-2">
        <label className="flex flex-col gap-1 text-xs text-zinc-700">
          <span className="font-medium text-zinc-800">
            What second should we start tracking you? Pick 1–2 seconds before
            the gather or first step — not the shot itself.
          </span>
          <input
            type="number"
            min={0}
            max={duration ?? undefined}
            step={0.1}
            value={secondInput}
            onChange={(event) => setSecondInput(event.target.value)}
            className="w-28 rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm outline-none ring-orange-600 focus:ring-2"
          />
        </label>
        {maxHint ? <p className="text-[11px] text-zinc-500">{maxHint} Use 0 for the start.</p> : null}
        <button
          type="submit"
          disabled={loading}
          className="rounded-md border border-zinc-300 bg-white px-2.5 py-1.5 text-xs font-medium text-zinc-800 hover:bg-zinc-50 disabled:opacity-60"
        >
          {loading ? "Loading…" : "Show this second"}
        </button>
      </form>

      {error && !src ? <p className="text-xs text-red-600">{error}</p> : null}

      {src ? (
        <>
          <p className="text-xs text-zinc-600">
            Draw a rectangle around <span className="font-medium">you only</span> at{" "}
            {startS?.toFixed(1)}s. Works with a finger on mobile.
          </p>
          <div
            className="relative inline-block max-w-full cursor-crosshair touch-none select-none overflow-hidden rounded-lg border border-zinc-200"
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
          >
            <img
              ref={imgRef}
              src={src}
              alt={`Frame at ${startS ?? 0} seconds`}
              draggable={false}
              className="block max-h-80 w-full bg-black sm:max-h-96"
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
            onClick={() => void onSave()}
            disabled={saving}
            className="min-h-10 rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            {saving ? "Saving…" : "Save box and process"}
          </button>
        </>
      ) : null}
    </div>
  );
}
