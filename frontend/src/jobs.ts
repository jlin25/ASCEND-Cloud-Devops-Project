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
  { type: "image_resize", label: "Resize image", description: "Scale an image to an exact size", accept: "image/*" },
  { type: "deblur", label: "Deblur image", description: "Sharpen a blurry photo", accept: "image/*" },
  { type: "trim", label: "Trim video", description: "Keep only part of a video", accept: "video/*" },
  { type: "video_quality", label: "Change resolution", description: "Re-encode at 720p, 1080p or 4K", accept: "video/*" },
  {
    type: "format_converter",
    label: "Convert format",
    description: "Change an image or video's file type",
    accept: "image/*,video/*",
  },
] as const;

export type JobType = (typeof JOB_TYPES)[number]["type"];

export const LABELS: Record<string, string> = Object.fromEntries(JOB_TYPES.map((j) => [j.type, j.label]));

// S3 keys look like uploads/<user>/<uuid>-<filename> (backend/s3_client.py);
// strip the folders and the uuid prefix to get back the name the user uploaded.
export function basename(key: string) {
  const name = key.split("/").pop() ?? key;
  return name.replace(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-/i, "") || name;
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
