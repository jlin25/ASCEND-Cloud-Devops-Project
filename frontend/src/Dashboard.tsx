import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type CreateTaskBody } from "./api";
import {
  convertTargets,
  displayName,
  extension,
  JOB_TYPES,
  LABELS,
  planFiles,
  type Job,
  type JobType,
  type Skipped,
} from "./jobs";
import Sidebar from "./Sidebar";
import JobDetail from "./JobDetail";
import RunSummary, { type Run } from "./RunSummary";

const RESOLUTIONS = ["720p", "1080p", "4k"] as const;
const AUDIO_FORMATS = ["mp3", "wav", "aac"] as const;

// How many files upload at once in a folder run. Unlimited files overall; this
// just stops the browser from sending hundreds of uploads in parallel.
const UPLOAD_CONCURRENCY = 3;

// The last folder run survives a reload (per user, since one browser may be shared).
// Storage can be unavailable (private windows, blocked site data), so never let it break the page.
const runKey = (username: string) => `ascend.lastRun.${username}`;

function loadRun(username: string): Run | null {
  try {
    const raw = localStorage.getItem(runKey(username));
    return raw ? (JSON.parse(raw) as Run) : null;
  } catch {
    return null;
  }
}

function saveRun(username: string, run: Run | null) {
  try {
    if (run) localStorage.setItem(runKey(username), JSON.stringify(run));
    else localStorage.removeItem(runKey(username));
  } catch {
    // Not remembered across reloads; everything else still works.
  }
}

export default function Dashboard({ username, onLogout }: { username: string; onLogout: () => void }) {
  const [jobs, setJobs] = useState<Job[]>([]);
  // Job shown in the main panel; null shows the new-job form.
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Sidebar visibility on narrow screens (always visible on desktop).
  const [sidebarOpen, setSidebarOpen] = useState(false);
  // Picked files: one file, several files, or every file in a folder.
  const [files, setFiles] = useState<File[]>([]);
  const [type, setType] = useState<JobType>("image_resize");
  const [params, setParams] = useState({
    width: "800",
    height: "600",
    start: "0",
    end: "10",
    resolution: "1080p",
    audio: "mp3",
    output: "",
  });
  const [submitting, setSubmitting] = useState(false);
  // Upload progress for a multi-file submit.
  const [uploading, setUploading] = useState<{ done: number; total: number } | null>(null);
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);
  // Bumped after each submit to remount the file inputs, so picking the same files again fires onChange.
  const [fileInputKey, setFileInputKey] = useState(0);
  const [lastRun, setLastRunState] = useState<Run | null>(() => loadRun(username));

  const setLastRun = useCallback(
    (update: Run | null | ((prev: Run | null) => Run | null)) => {
      setLastRunState((prev) => {
        const next = typeof update === "function" ? update(prev) : update;
        saveRun(username, next);
        return next;
      });
    },
    [username],
  );

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

  // Poll while anything is still in flight, often enough for progress bars to move smoothly.
  const active = jobs.some((j) => j.status === "pending" || j.status === "processing");
  useEffect(() => {
    if (!active) return;
    const id = setInterval(refresh, 2000);
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

  function select(id: string | null) {
    setSelectedId(id);
    setSidebarOpen(false);
  }

  const outputFormats = convertTargets(files);
  const output = outputFormats.includes(params.output) ? params.output : outputFormats[0] ?? "";
  // Which picked files this job will actually run on (the rest are skipped, with a reason).
  const { run, skipped } = planFiles(files, type, output);
  const isFolder = files.some((f) => f.webkitRelativePath);
  const folderName = isFolder ? files[0].webkitRelativePath.split("/")[0] : null;

  const set = (key: keyof typeof params) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setParams({ ...params, [key]: e.target.value });

  // Settings only; per-file problems (wrong kind, already in the target format, ...) are skips, not errors.
  function validate(): string | null {
    if (type === "image_resize" && !(Number(params.width) >= 1 && Number(params.height) >= 1)) {
      return "Width and height must be at least 1";
    }
    if (type === "trim") {
      if (params.start === "" || params.end === "" || !(Number(params.start) >= 0)) return "Enter a start and end time";
      if (!(Number(params.end) > Number(params.start))) return "End must be after start";
    }
    if (files.length > 0 && run.length === 0) {
      return files.length === 1 ? `Can't run on this file: ${skipped[0]?.reason}` : "None of these files can be used for this job";
    }
    return null;
  }
  const invalid = validate();

  function buildJob(file_url: string, file: File): CreateTaskBody {
    switch (type) {
      case "image_resize":
        return { type, file_url, width: Number(params.width), height: Number(params.height) };
      case "deblur":
        return { type, file_url };
      case "trim":
        return { type, file_url, start_seconds: Number(params.start), end_seconds: Number(params.end) };
      case "video_quality":
        return { type, file_url, resolution: params.resolution as (typeof RESOLUTIONS)[number] };
      case "extract_audio":
        return { type, file_url, format: params.audio as (typeof AUDIO_FORMATS)[number] };
      case "format_converter":
        return {
          type,
          file_url,
          // Each file's own format, so a folder can mix .jpg and .png.
          input_format: extension(file.name) as "mp4",
          output_format: output as "mp4",
        };
    }
  }

  async function submitOne(file: File): Promise<string> {
    const { file_key } = await api.upload(file);
    const { task_id } = (await api.createTask(buildJob(file_key, file))) as { task_id: string };
    return task_id;
  }

  // Upload several files
  async function submitAll(toRun: File[]) {
    const taskIds: string[] = [];
    const failed: Skipped[] = [];
    let next = 0;
    let done = 0;
    let stopped = false;
    setUploading({ done: 0, total: toRun.length });

    async function lane() {
      while (!stopped && next < toRun.length) {
        const file = toRun[next++];
        try {
          taskIds.push(await submitOne(file));
        } catch (err) {
          if (err instanceof ApiError && err.status === 401) {
            stopped = true;
            throw err;
          }
          failed.push({ name: displayName(file), reason: err instanceof ApiError ? err.message : "upload failed" });
        }
        done++;
        setUploading({ done, total: toRun.length });
        if (done % 10 === 0) refresh();
      }
    }

    await Promise.all(Array.from({ length: Math.min(UPLOAD_CONCURRENCY, toRun.length) }, lane));
    return { taskIds, failed };
  }

  function resetPicker() {
    setFiles([]);
    setFileInputKey((k) => k + 1);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (run.length === 0 || invalid) return;
    setSubmitting(true);
    setMessage(null);
    try {
      if (files.length === 1) {
        const task_id = await submitOne(run[0]);
        resetPicker();
        setMessage({ text: `Submitted ${run[0].name}` });
        await refresh();
        setSelectedId(task_id);
        return;
      }

      // Several files / a folder: submit them all, then show the run summary.
      // An older run's ZIP is replaced, so clean it up first.
      if (lastRun?.bundleId) api.deleteBundle(lastRun.bundleId).catch(() => {});
      const label = `${folderName ? `${files.length} files from ${folderName}` : `${files.length} files`} · ${LABELS[type]}`;
      const { taskIds, failed } = await submitAll(run);
      setLastRun({ label, taskIds, skipped, failedUploads: failed, createdAt: new Date().toISOString() });
      resetPicker();
      setMessage(
        failed.length
          ? { text: `Submitted ${taskIds.length} of ${run.length} files; ${failed.length} failed to upload`, error: true }
          : { text: `Submitted ${taskIds.length} files` },
      );
      await refresh();
    } catch (err) {
      fail(err, "Submit failed");
    } finally {
      setSubmitting(false);
      setUploading(null);
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

  const setRunBundle = useCallback(
    (bundleId: string | undefined) => setLastRun((prev) => (prev ? { ...prev, bundleId } : prev)),
    [setLastRun],
  );
  const closeRun = useCallback(() => setLastRun(null), [setLastRun]);

  const what = jobType.accept === "image/*" ? "an image" : jobType.accept === "video/*" ? "a video" : "an image or video";
  const choosePrompt = `Click to choose ${what}…`;
  const pickedLabel =
    files.length === 0
      ? choosePrompt
      : files.length === 1
        ? files[0].name
        : folderName
          ? `${files.length} files from ${folderName}`
          : `${files.length} files`;

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
          <JobDetail key={selectedJob.id} job={selectedJob} onDelete={handleDelete} />
        ) : (
          <>
            <div>
              <h1 className="page-title">New job</h1>
              <p className="muted">
                Pick what to do, add a file or folder and press Run. Your uploads appear on the left.
              </p>
            </div>

            {lastRun && (
              <RunSummary
                run={lastRun}
                jobs={jobs}
                onSelect={select}
                onBundleChange={setRunBundle}
                onClose={closeRun}
                onError={fail}
              />
            )}

            <form className="card submit" onSubmit={handleSubmit}>
              <div className="field">
                <span className="field-label">1. What do you want to do?</span>
                <div className="type-grid">
                  {JOB_TYPES.map((j) => (
                    <button
                      key={j.type}
                      type="button"
                      className={`type-option${type === j.type ? " active" : ""}`}
                      onClick={() => setType(j.type)}
                    >
                      <span className="type-name">{j.label}</span>
                      <span className="muted">{j.description}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="field">
                <span className="field-label">2. Choose a file or folder</span>
                <div className="pickers">
                  <label className={`file${files.length && !isFolder ? " chosen" : ""}`}>
                    <input
                      key={`files-${fileInputKey}`}
                      type="file"
                      multiple
                      accept={jobType.accept}
                      onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
                    />
                    {isFolder ? choosePrompt : pickedLabel}
                  </label>
                  <label className={`file folder${isFolder ? " chosen" : ""}`}>
                    <input
                      key={`folder-${fileInputKey}`}
                      type="file"
                      ref={(el) => el?.setAttribute("webkitdirectory", "")}
                      onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
                    />
                    {isFolder ? pickedLabel : "Choose a folder…"}
                  </label>
                </div>
                {files.length > 1 && (
                  <p className="hint muted">
                    {run.length} {run.length === 1 ? "file" : "files"} will run
                    {skipped.length > 0 && ` · ${skipped.length} skipped`}
                  </p>
                )}
                {files.length > 1 && skipped.length > 0 && (
                  <details className="run-files">
                    <summary className="muted">Skipped files ({skipped.length})</summary>
                    <ul className="run-list">
                      {skipped.map((s, i) => (
                        <li key={i} className="run-skip">
                          <span className="side-name">{s.name}</span>
                          <span className="muted">{s.reason}</span>
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
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
                    {type === "extract_audio" && (
                      <label className="inline">
                        Format
                        <select value={params.audio} onChange={set("audio")}>
                          {AUDIO_FORMATS.map((f) => (
                            <option key={f}>{f}</option>
                          ))}
                        </select>
                      </label>
                    )}
                    {type === "format_converter" &&
                      (outputFormats.length > 0 ? (
                        <label className="inline">
                          {files.length === 1 ? `.${extension(files[0].name)} to` : "Convert to"}
                          <select value={output} onChange={set("output")}>
                            {outputFormats.map((f) => (
                              <option key={f}>{f}</option>
                            ))}
                          </select>
                        </label>
                      ) : (
                        <span className="muted">
                          {files.length === 0 ? "Choose a file first to pick the output format." : "No convertible files chosen."}
                        </span>
                      ))}
                  </div>
                </div>
              )}

              <div className="form-foot">
                {invalid && <span className="hint muted">{invalid}</span>}
                <button className="primary" type="submit" disabled={run.length === 0 || !!invalid || submitting}>
                  {uploading
                    ? `Uploading ${uploading.done} of ${uploading.total}…`
                    : submitting
                      ? "Uploading…"
                      : run.length > 1
                        ? `Run on ${run.length} files`
                        : "Run"}
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
