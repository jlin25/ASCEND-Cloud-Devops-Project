// Shared job types and display helpers for the dashboard, sidebar and job view.

export type Job = {
  id: string;
  job_type: string;
  input_key: string;
  output_key: string | null;
  status: "pending" | "processing" | "done" | "failed";
  // Percent complete (0–99 while processing, 100 once done). Only video and
  // audio jobs report real values; the worker leaves the rest at 0 until done.
  progress: number | null;
  created_at: string;
};

// Only the job types the worker actually implements (see backend/worker.py).
export const JOB_TYPES = [
  { type: "image_resize", label: "Resize image", description: "Scale an image to an exact size", accept: "image/*" },
  { type: "deblur", label: "Deblur image", description: "Sharpen a blurry photo", accept: "image/*" },
  { type: "trim", label: "Trim video", description: "Keep only part of a video", accept: "video/*" },
  { type: "video_quality", label: "Change resolution", description: "Re-encode at 720p, 1080p or 4K", accept: "video/*" },
  { type: "extract_audio", label: "Extract audio", description: "Save a video's sound as MP3, WAV or AAC", accept: "video/*" },
  {
    type: "format_converter",
    label: "Convert format",
    description: "Change an image or video's file type",
    accept: "image/*,video/*",
  },
] as const;

export type JobType = (typeof JOB_TYPES)[number]["type"];

export const VIDEO_FORMATS = ["mp4", "mov", "avi", "webm"];
export const IMAGE_FORMATS = ["jpg", "png", "webp"];

export function extension(name: string) {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  return ext === "jpeg" ? "jpg" : ext;
}

export function displayName(file: File) {
  return file.webkitRelativePath || file.name;
}

function kindOf(file: File): "image" | "video" | null {
  if (file.type.startsWith("image/")) return "image";
  if (file.type.startsWith("video/")) return "video";
  const ext = extension(file.name);
  if ([...IMAGE_FORMATS, "gif"].includes(ext)) return "image";
  if (VIDEO_FORMATS.includes(ext)) return "video";
  return null;
}

// Files the OS drops into folders that shouldn't be processed.
const SYSTEM_FILES = new Set(["thumbs.db", "desktop.ini"]);

export type Skipped = { name: string; reason: string };

export function convertTargets(files: File[]): string[] {
  const kinds = new Set(files.map(kindOf));
  const targets = [...(kinds.has("image") ? IMAGE_FORMATS : []), ...(kinds.has("video") ? VIDEO_FORMATS : [])];
  return files.length === 1 ? targets.filter((f) => f !== extension(files[0].name)) : targets;
}

// Split picked files into the ones this job will run on and the ones it skips
 
export function planFiles(files: File[], type: JobType, output: string): { run: File[]; skipped: Skipped[] } {
  const accept = JOB_TYPES.find((j) => j.type === type)!.accept;
  const wanted = accept === "image/*" ? ["image"] : accept === "video/*" ? ["video"] : ["image", "video"];
  const run: File[] = [];
  const skipped: Skipped[] = [];
  const skip = (file: File, reason: string) => skipped.push({ name: displayName(file), reason });

  for (const file of files) {
    const kind = kindOf(file);
    if (file.name.startsWith(".") || SYSTEM_FILES.has(file.name.toLowerCase())) {
      skip(file, "system file");
    } else if (!kind || !wanted.includes(kind)) {
      skip(file, wanted.length === 2 ? "not an image or video" : `not ${wanted[0] === "image" ? "an image" : "a video"}`);
    } else if (type === "format_converter") {
      const ext = extension(file.name);
      const targetIsVideo = VIDEO_FORMATS.includes(output);
      if (![...VIDEO_FORMATS, ...IMAGE_FORMATS].includes(ext)) skip(file, `can't convert .${ext} files`);
      else if (VIDEO_FORMATS.includes(ext) !== targetIsVideo)
        skip(file, targetIsVideo ? "can't convert an image to a video" : "can't convert a video to an image");
      else if (ext === output) skip(file, `already .${output}`);
      else run.push(file);
    } else {
      run.push(file);
    }
  }
  return { run, skipped };
}

export const LABELS: Record<string, string> = Object.fromEntries(JOB_TYPES.map((j) => [j.type, j.label]));

// S3 keys look like uploads/<user>/<uuid>-<filename> (backend/s3_client.py);
// strip the folders and the uuid prefix to get back the name the user uploaded.
export function basename(key: string) {
  const name = key.split("/").pop() ?? key;
  return name.replace(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-/i, "") || name;
}

export function mediaKind(key: string): "image" | "video" | "audio" | null {
  const ext = key.split(".").pop()?.toLowerCase() ?? "";
  if (["jpg", "jpeg", "png", "webp", "gif"].includes(ext)) return "image";
  if (["mp4", "webm", "mov"].includes(ext)) return "video";
  if (["mp3", "wav", "aac", "m4a"].includes(ext)) return "audio";
  return null;
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
