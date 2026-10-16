import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type CreateTaskBody } from "./api";

type Job = {
  id: string;
  job_type: string;
  input_key: string;
  output_key: string | null;
  status: "pending" | "processing" | "done" | "failed";
  created_at: string;
};

const VIDEO_FORMATS = ["mp4", "mov", "avi", "webm"];
const IMAGE_FORMATS = ["jpg", "png", "webp"];
const RESOLUTIONS = ["720p", "1080p", "4k"] as const;

// Only the job types the worker actually implements (see backend/worker.py).
const JOB_TYPES = [
  { type: "image_resize", label: "Resize image", accept: "image/*" },
  { type: "deblur", label: "Deblur image", accept: "image/*" },
  { type: "trim", label: "Trim video", accept: "video/*" },
  { type: "video_quality", label: "Change resolution", accept: "video/*" },
  { type: "format_converter", label: "Convert format", accept: "image/*,video/*" },
] as const;

type JobType = (typeof JOB_TYPES)[number]["type"];

const LABELS: Record<string, string> = Object.fromEntries(JOB_TYPES.map((j) => [j.type, j.label]));

function extension(name: string) {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  return ext === "jpeg" ? "jpg" : ext;
}

function basename(key: string) {
  return key.split("/").pop() ?? key;
}

export default function Dashboard({ username, onLogout }: { username: string; onLogout: () => void }) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [type, setType] = useState<JobType>("image_resize");
  const [params, setParams] = useState({
    width: "800",
    height: "600",
    start: "0",
    end: "10",
    resolution: "1080p",
    output: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);

  const fail = useCallback(
    (err: unknown, prefix: string) => {
      if (err instanceof ApiError && err.status === 401) return onLogout();
      setMessage({ text: `${prefix}: ${err instanceof ApiError ? err.message : "something went wrong"}`, error: true });
    },
    [onLogout],
  );

  const refresh = useCallback(async () => {
    try {
      const data = (await api.listTasks()) as { tasks: Job[] };
      setJobs(data.tasks.sort((a, b) => b.created_at.localeCompare(a.created_at)));
    } catch (err) {
      fail(err, "Couldn't load jobs");
    }
  }, [fail]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-mount
    refresh();
  }, [refresh]);

  // Poll while anything is still in flight.
  const active = jobs.some((j) => j.status === "pending" || j.status === "processing");
  useEffect(() => {
    if (!active) return;
    const id = setInterval(refresh, 4000);
    return () => clearInterval(id);
  }, [active, refresh]);

  const ext = file ? extension(file.name) : "";
  const outputFormats = (VIDEO_FORMATS.includes(ext) ? VIDEO_FORMATS : IMAGE_FORMATS).filter((f) => f !== ext);
  const output = outputFormats.includes(params.output) ? params.output : outputFormats[0];
  const set = (key: keyof typeof params) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setParams({ ...params, [key]: e.target.value });

  function buildJob(file_url: string): CreateTaskBody {
    switch (type) {
      case "image_resize":
        return { type, file_url, width: Number(params.width), height: Number(params.height) };
      case "deblur":
        return { type, file_url };
      case "trim":
        return { type, file_url, start_seconds: Number(params.start), end_seconds: Number(params.end) };
      case "video_quality":
        return { type, file_url, resolution: params.resolution as (typeof RESOLUTIONS)[number] };
      case "format_converter":
        return {
          type,
          file_url,
          input_format: ext as "mp4",
          output_format: output as "mp4",
        };
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    if (type === "format_converter" && ![...VIDEO_FORMATS, ...IMAGE_FORMATS].includes(ext)) {
      return setMessage({ text: `Can't convert .${ext} files`, error: true });
    }
    setSubmitting(true);
    setMessage(null);
    try {
      const { file_key } = await api.upload(file);
      await api.createTask(buildJob(file_key));
      setFile(null);
      setMessage({ text: `Submitted ${file.name}` });
      await refresh();
    } catch (err) {
      fail(err, "Submit failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDownload(id: string) {
    try {
      const data = (await api.getTaskResult(id)) as { output_file_url: string };
      window.open(data.output_file_url, "_blank");
    } catch (err) {
      fail(err, "Couldn't get result");
    }
  }

  async function handleDelete(id: string) {
    try {
      await api.deleteTask(id);
      setJobs(jobs.filter((j) => j.id !== id));
    } catch (err) {
      fail(err, "Delete failed");
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <span className="logo">ASCEND</span>
        <span className="muted">{username}</span>
        <button className="link" onClick={onLogout}>
          Log out
        </button>
      </header>

      <form className="card submit" onSubmit={handleSubmit}>
        <select value={type} onChange={(e) => setType(e.target.value as JobType)}>
          {JOB_TYPES.map((j) => (
            <option key={j.type} value={j.type}>
              {j.label}
            </option>
          ))}
        </select>

        <label className="file">
          <input
            key={type}
            type="file"
            accept={JOB_TYPES.find((j) => j.type === type)?.accept}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          {file ? file.name : "Choose file…"}
        </label>

        {type === "image_resize" && (
          <>
            <input className="num" type="number" min={1} value={params.width} onChange={set("width")} title="Width" />
            <span className="muted">×</span>
            <input className="num" type="number" min={1} value={params.height} onChange={set("height")} title="Height" />
          </>
        )}
        {type === "trim" && (
          <>
            <input className="num" type="number" min={0} step="any" value={params.start} onChange={set("start")} title="Start (s)" />
            <span className="muted">to</span>
            <input className="num" type="number" min={0} step="any" value={params.end} onChange={set("end")} title="End (s)" />
            <span className="muted">s</span>
          </>
        )}
        {type === "video_quality" && (
          <select value={params.resolution} onChange={set("resolution")}>
            {RESOLUTIONS.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        )}
        {type === "format_converter" && file && (
          <>
            <span className="muted">.{ext} →</span>
            <select value={output} onChange={set("output")}>
              {outputFormats.map((f) => (
                <option key={f}>{f}</option>
              ))}
            </select>
          </>
        )}

        <button className="primary" type="submit" disabled={!file || submitting}>
          {submitting ? "Uploading…" : "Run"}
        </button>
      </form>

      {message && <p className={message.error ? "error" : "muted"}>{message.text}</p>}

      <section className="card">
        <div className="card-head">
          <h2>Jobs</h2>
          <button className="link" onClick={refresh}>
            Refresh
          </button>
        </div>
        {jobs.length === 0 ? (
          <p className="muted empty">No jobs yet.</p>
        ) : (
          <table>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id}>
                  <td>
                    <span className={`badge ${job.status}`}>{job.status}</span>
                  </td>
                  <td className="name" title={job.input_key}>
                    {basename(job.input_key)}
                  </td>
                  <td className="muted">{LABELS[job.job_type] ?? job.job_type}</td>
                  <td className="muted">{new Date(job.created_at).toLocaleString()}</td>
                  <td className="actions">
                    {job.status === "done" && (
                      <button className="link" onClick={() => handleDownload(job.id)}>
                        Download
                      </button>
                    )}
                    <button className="link danger" onClick={() => handleDelete(job.id)} title="Delete">
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
