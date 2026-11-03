// Shared job types and display helpers for the dashboard, sidebar and job view.

export type Job = {
  id: string;
  job_type: string;
  input_key: string;
  output_key: string | null;
  status: "pending" | "processing" | "done" | "failed";
  created_at: string;
};

// Only the job types the worker actually implements (see backend/worker.py).
export const JOB_TYPES = [
  { type: "image_resize", label: "Resize image", accept: "image/*" },
  { type: "deblur", label: "Deblur image", accept: "image/*" },
  { type: "trim", label: "Trim video", accept: "video/*" },
  { type: "video_quality", label: "Change resolution", accept: "video/*" },
  { type: "format_converter", label: "Convert format", accept: "image/*,video/*" },
] as const;

export type JobType = (typeof JOB_TYPES)[number]["type"];

export const LABELS: Record<string, string> = Object.fromEntries(JOB_TYPES.map((j) => [j.type, j.label]));

export function basename(key: string) {
  return key.split("/").pop() ?? key;
}

// created_at is a TIMESTAMP without time zone (UTC on the server), so the
// string carries no offset — read it as UTC instead of local time.
export function parseUtc(s: string) {
  return new Date(/(Z|[+-]\d\d:?\d\d)$/i.test(s) ? s : `${s}Z`);
}

const relative = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

export function timeAgo(date: Date) {
  const seconds = (date.getTime() - Date.now()) / 1000;
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return relative.format(Math.trunc(seconds / size), unit);
  }
  return "just now";
}
