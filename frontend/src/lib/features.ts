export const FEATURE_LABELS: Record<string, string> = {
  release_angle: "Release angle",
  elbow_angle_at_release: "Elbow at release",
  release_height_ratio: "Release height",
  shot_arc: "Shot arc",
  arm_extension_at_release: "Arm extension",
  release_point_consistency: "Release consistency",
  decision_speed: "Decision speed",
  first_step_burst: "First-step burst",
  change_of_direction_angle: "Change of direction",
};

export const FEATURE_UNITS: Record<string, string> = {
  release_angle: "°",
  elbow_angle_at_release: "°",
  release_height_ratio: "× standing",
  shot_arc: "× standing",
  arm_extension_at_release: "°",
  release_point_consistency: "",
  decision_speed: " frames",
  first_step_burst: " body-lengths",
  change_of_direction_angle: "°",
};

export const FEATURE_BAR_MAX: Record<string, number> = {
  release_angle: 90,
  elbow_angle_at_release: 180,
  release_height_ratio: 1.4,
  shot_arc: 0.5,
  arm_extension_at_release: 180,
  release_point_consistency: 0.3,
  decision_speed: 60,
  first_step_burst: 1.5,
  change_of_direction_angle: 180,
};

export const STYLE_LABELS: Record<string, string> = {
  size: "Size",
  perimeter_vs_rim: "Perimeter vs rim",
  creation: "Creation",
  drive_burst: "Drive burst",
  passing: "Passing",
  catch_readiness: "Catch readiness",
  rim_pressure_tendency: "Rim-pressure tendency",
  playmaking_orientation: "Playmaking orientation",
};

export function featureLabel(name: string): string {
  return FEATURE_LABELS[name] ?? name.replace(/_/g, " ");
}

export function formatFeatureValue(name: string, value: number): string {
  const unit = FEATURE_UNITS[name] ?? "";
  const digits = Math.abs(value) >= 10 ? 1 : 2;
  return `${value.toFixed(digits)}${unit}`;
}

export function formatHeightIn(heightIn: number): string {
  const feet = Math.floor(heightIn / 12);
  const inches = Math.round(heightIn % 12);
  return `${feet}'${inches}"`;
}
