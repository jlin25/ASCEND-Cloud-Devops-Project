import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type CreateTaskBody } from "./api";
import { JOB_TYPES, type Job, type JobType } from "./jobs";
import Sidebar from "./Sidebar";
import JobDetail from "./JobDetail";

const VIDEO_FORMATS = ["mp4", "mov", "avi", "webm"];
const IMAGE_FORMATS = ["jpg", "png", "webp"];
const RESOLUTIONS = ["720p", "1080p", "4k"] as const;

function extension(name: string) {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  return ext === "jpeg" ? "jpg" : ext;
}

export default function Dashboard({ username, onLogout }: { username: string; onLogout: () => void }) {
  const [jobs, setJobs] = useState<Job[]>([]);
  // Job shown in the main panel; null shows the new-job form.
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Sidebar visibility on narrow screens (always visible on desktop).
  const [sidebarOpen, setSidebarOpen] = useState(false);
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
  // Bumped after each submit to remount the file input, so picking the same file again fires onChange.
  const [fileInputKey, setFileInputKey] = useState(0);

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

  // Success messages fade out on their own; errors stay until the next action.
  useEffect(() => {
    if (!message || message.error) return;
    const id = setTimeout(() => setMessage(null), 4000);
    return () => clearTimeout(id);
  }, [message]);

  // Re-render periodically so relative times ("2 minutes ago") stay current.
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 30000);
    return () => clearInterval(id);
  }, []);

  const selectedJob = jobs.find((j) => j.id === selectedId);
  const jobType = JOB_TYPES.find((j) => j.type === type)!;

  // Keep the chosen file when switching job type only if the new type accepts it.
  function changeType(next: JobType) {
    const accept = JOB_TYPES.find((j) => j.type === next)!.accept;
    if (file && !accept.split(",").some((a) => file.type.startsWith(a.replace("*", "")))) setFile(null);
    setType(next);
  }

  function select(id: string | null) {
    setSelectedId(id);
    setSidebarOpen(false);
  }

  const ext = file ? extension(file.name) : "";
  const outputFormats = (VIDEO_FORMATS.includes(ext) ? VIDEO_FORMATS : IMAGE_FORMATS).filter((f) => f !== ext);
  const output = outputFormats.includes(params.output) ? params.output : outputFormats[0];
  const set = (key: keyof typeof params) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setParams({ ...params, [key]: e.target.value });

  function validate(): string | null {
    if (type === "image_resize" && !(Number(params.width) >= 1 && Number(params.height) >= 1)) {
      return "Width and height must be at least 1";
    }
    if (type === "trim") {
      if (params.start === "" || params.end === "" || !(Number(params.start) >= 0)) return "Enter a start and end time";
      if (!(Number(params.end) > Number(params.start))) return "End must be after start";
    }
    if (type === "format_converter" && file && ![...VIDEO_FORMATS, ...IMAGE_FORMATS].includes(ext)) {
      return `Can't convert .${ext} files`;
    }
    return null;
  }
  const invalid = validate();

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
    if (!file || invalid) return;
    setSubmitting(true);
    setMessage(null);
    try {
      const { file_key } = await api.upload(file);
      const { task_id } = (await api.createTask(buildJob(file_key))) as { task_id: string };
      setFile(null);
      setFileInputKey((k) => k + 1);
      setMessage({ text: `Submitted ${file.name}` });
      await refresh();
      // Jump to the new job so its progress is visible straight away.
      setSelectedId(task_id);
    } catch (err) {
      fail(err, "Submit failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDownload(id: string) {
    // Open the tab during the click itself so popup blockers allow it, then
    // point it at the presigned URL once the request comes back.
    const tab = window.open("", "_blank");
    try {
      const data = (await api.getTaskResult(id)) as { output_file_url: string };
      if (tab) {
        tab.opener = null;
        tab.location.href = data.output_file_url;
      } else {
        window.open(data.output_file_url, "_blank", "noopener");
      }
    } catch (err) {
      tab?.close();
      fail(err, "Couldn't get result");
    }
  }

  async function handleDelete(id: string) {
    try {
      await api.deleteTask(id);
      setJobs(jobs.filter((j) => j.id !== id));
      if (selectedId === id) setSelectedId(null);
    } catch (err) {
      fail(err, "Delete failed");
    }
  }

  return (
    <div className="shell">
      <Sidebar
        username={username}
        jobs={jobs}
        selectedId={selectedJob ? selectedId : null}
        open={sidebarOpen}
        onSelect={select}
        onRefresh={refresh}
        onLogout={onLogout}
      />
      {sidebarOpen && <div className="scrim" onClick={() => setSidebarOpen(false)} />}

      <main className="main">
        <header className="mobile-bar">
          <button className="link menu-button" onClick={() => setSidebarOpen(true)} aria-label="Open menu">
            ☰
          </button>
          <span className="logo">ASCEND</span>
        </header>

        {selectedJob ? (
          <JobDetail key={selectedJob.id} job={selectedJob} onDownload={handleDownload} onDelete={handleDelete} />
        ) : (
          <>
            <div>
              <h1 className="page-title">New job</h1>
              <p className="muted">Pick what to do, add a file and press Run. Your uploads appear on the left.</p>
            </div>
            <form className="card submit" onSubmit={handleSubmit}>
              <div className="field">
                <span className="field-label">1. What do you want to do?</span>
                <div className="type-grid">
                  {JOB_TYPES.map((j) => (
                    <button
                      key={j.type}
                      type="button"
                      className={`type-option${type === j.type ? " active" : ""}`}
                      onClick={() => changeType(j.type)}
                    >
                      <span className="type-name">{j.label}</span>
                      <span className="muted">{j.description}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="field">
                <span className="field-label">2. Choose a file</span>
                <label className={`file${file ? " chosen" : ""}`}>
                  <input
                    key={`${type}-${fileInputKey}`}
                    type="file"
                    accept={jobType.accept}
                    onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  />
                  {file
                    ? file.name
                    : `Click to choose ${jobType.accept === "image/*" ? "an image" : jobType.accept === "video/*" ? "a video" : "an image or video"}…`}
                </label>
              </div>

              {type !== "deblur" && (
                <div className="field">
                  <span className="field-label">3. Options</span>
                  <div className="row">
                    {type === "image_resize" && (
                      <>
                        <label className="inline">
                          Width <input className="num" type="number" min={1} value={params.width} onChange={set("width")} />
                        </label>
                        <label className="inline">
                          Height <input className="num" type="number" min={1} value={params.height} onChange={set("height")} />
                        </label>
                        <span className="muted">px</span>
                      </>
                    )}
                    {type === "trim" && (
                      <>
                        <label className="inline">
                          Start <input className="num" type="number" min={0} step="any" value={params.start} onChange={set("start")} />
                        </label>
                        <label className="inline">
                          End <input className="num" type="number" min={0} step="any" value={params.end} onChange={set("end")} />
                        </label>
                        <span className="muted">seconds</span>
                      </>
                    )}
                    {type === "video_quality" && (
                      <label className="inline">
                        Resolution
                        <select value={params.resolution} onChange={set("resolution")}>
                          {RESOLUTIONS.map((r) => (
                            <option key={r}>{r}</option>
                          ))}
                        </select>
                      </label>
                    )}
                    {type === "format_converter" &&
                      (file ? (
                        <label className="inline">
                          .{ext} to
                          <select value={output} onChange={set("output")}>
                            {outputFormats.map((f) => (
                              <option key={f}>{f}</option>
                            ))}
                          </select>
                        </label>
                      ) : (
                        <span className="muted">Choose a file first to pick the output format.</span>
                      ))}
                  </div>
                </div>
              )}

              <div className="form-foot">
                {invalid && <span className="hint muted">{invalid}</span>}
                <button className="primary" type="submit" disabled={!file || !!invalid || submitting}>
                  {submitting ? "Uploading…" : "Run"}
                </button>
              </div>
            </form>
          </>
        )}

        {message && <p className={message.error ? "error" : "muted"}>{message.text}</p>}
      </main>
    </div>
  );
}
