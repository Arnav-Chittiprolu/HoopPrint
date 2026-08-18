"use client";

import type { DominantHand, PlayerPosition, PrimarySkill, ProfileQuestionnaire } from "@/lib/api";
import { formatHeightIn, splitHeightIn } from "@/lib/features";
import { initialsFromName, PROFILE_FIELD_CLASS } from "@/lib/profile";

type Props = {
  form: ProfileQuestionnaire;
  setForm: (next: ProfileQuestionnaire | ((prev: ProfileQuestionnaire) => ProfileQuestionnaire)) => void;
  required?: boolean;
};

export function ProfileFields({ form, setForm, required = false }: Props) {
  const { feet, inches } = splitHeightIn(form.height_in);
  const initials = initialsFromName(form.display_name);

  function setHeight(nextFeet: number | "", nextInches: number | "") {
    if (nextFeet === "" && nextInches === "") {
      setForm((f) => ({ ...f, height_in: null }));
      return;
    }
    const f = nextFeet === "" ? 5 : nextFeet;
    const i = nextInches === "" ? 0 : nextInches;
    setForm((prev) => ({
      ...prev,
      height_in: Math.min(96, Math.max(48, Number(f) * 12 + Number(i))),
    }));
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="flex size-11 shrink-0 items-center justify-center rounded-full bg-zinc-100 text-sm font-medium text-zinc-500">
          {initials}
        </div>
        <label className="min-w-0 flex-1">
          <input
            required={required}
            value={form.display_name ?? ""}
            onChange={(e) =>
              setForm((f) => ({ ...f, display_name: e.target.value || null }))
            }
            placeholder="Display name"
            className={`${PROFILE_FIELD_CLASS} font-semibold`}
          />
          <span className="mt-1 block text-xs text-zinc-500">Display name</span>
        </label>
      </div>

      <div>
        <span className="text-sm font-medium text-zinc-800">Height</span>
        <div className="mt-1.5 grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-zinc-500">Feet</span>
            <select
              required={required}
              value={feet}
              onChange={(e) => {
                const next = e.target.value === "" ? "" : Number(e.target.value);
                setHeight(next, inches === "" ? 0 : inches);
              }}
              className={PROFILE_FIELD_CLASS}
            >
              <option value="">Select…</option>
              {[4, 5, 6, 7, 8].map((ft) => (
                <option key={ft} value={ft}>
                  {ft} ft
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-zinc-500">Inches</span>
            <select
              required={required}
              value={inches}
              onChange={(e) => {
                const next = e.target.value === "" ? "" : Number(e.target.value);
                setHeight(feet === "" ? 5 : feet, next);
              }}
              className={PROFILE_FIELD_CLASS}
            >
              <option value="">Select…</option>
              {Array.from({ length: 12 }, (_, i) => (
                <option key={i} value={i}>
                  {i} in
                </option>
              ))}
            </select>
          </label>
        </div>
        {form.height_in != null ? (
          <p className="mt-1.5 text-xs text-zinc-500">
            Preview: {formatHeightIn(form.height_in)} ({Math.round(form.height_in)})
          </p>
        ) : (
          <p className="mt-1.5 text-xs text-zinc-500">Stored as total inches internally.</p>
        )}
      </div>

      <label className="flex flex-col gap-1.5">
        <span className="text-sm font-medium text-zinc-800">Position</span>
        <select
          required={required}
          value={form.position ?? ""}
          onChange={(e) =>
            setForm((f) => ({
              ...f,
              position: (e.target.value || null) as PlayerPosition | null,
            }))
          }
          className={PROFILE_FIELD_CLASS}
        >
          <option value="">Select…</option>
          <option value="guard">Guard</option>
          <option value="wing">Wing</option>
          <option value="forward">Forward</option>
          <option value="center">Center</option>
        </select>
      </label>

      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-zinc-800">Dominant hand</span>
          <select
            required={required}
            value={form.dominant_hand ?? ""}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                dominant_hand: (e.target.value || null) as DominantHand | null,
              }))
            }
            className={PROFILE_FIELD_CLASS}
          >
            <option value="">Select…</option>
            <option value="right">Right</option>
            <option value="left">Left</option>
          </select>
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-zinc-800">Primary skill</span>
          <select
            required={required}
            value={form.primary_skill ?? ""}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                primary_skill: (e.target.value || null) as PrimarySkill | null,
              }))
            }
            className={PROFILE_FIELD_CLASS}
          >
            <option value="">Select…</option>
            <option value="shot">Shot</option>
            <option value="pass">Pass</option>
            <option value="drive">Drive</option>
          </select>
        </label>
      </div>

      <p className="text-xs leading-5 text-zinc-500">
        Height is body plausibility for NBA names, not a playing-style slot. Listed position is a
        weak preference.
      </p>
    </div>
  );
}
