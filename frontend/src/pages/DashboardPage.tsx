import { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { api, ApiError } from "../api";
import "./DashboardPage.css";

type Job = {
  id: string;
  job_type: string;
  input_key: string;
  output_key: string | null;
  status: string;
  created_at: string;
};

function basename(key: string) {
  return key.split("/").pop() ?? key;
}

const JOB_CATEGORIES: Record<string, string[]> = {
  "Video Editing": ["Video Upscale", "Format Converter", "Subtitle Generator", "AI Voiceover"],
  "Photo Editing": ["Image Resize/Upscale", "Background Removal", "Image Enhancement"],
};

const TASK_TYPE: Record<string, string> = {
  "Image Resize/Upscale": "image_resize",
};

const CATEGORIES = Object.keys(JOB_CATEGORIES);

const SIDEBAR_LINKS = [
  { icon: "🖥️", label: "Dashboard", path: "/dashboard" },
  { icon: "🛒", label: "Marketplace", path: "/marketplace" },
  { icon: "⚡", label: "My Jobs", path: "/jobs" },
  { icon: "💳", label: "Pricing", path: "/pricing" },
  { icon: "⚙️", label: "Settings", path: "/settings" },
];

export default function DashboardPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const username = localStorage.getItem("username") || "User";

  const [file, setFile] = useState<File | null>(null);
  const [category, setCategory] = useState(CATEGORIES[0]);
  const [task, setTask] = useState(JOB_CATEGORIES[CATEGORIES[0]][0]);
  const [dragOver, setDragOver] = useState(false);
  const [width, setWidth] = useState("800");
  const [height, setHeight] = useState("600");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [viewingId, setViewingId] = useState<string | null>(null);

  async function refreshJobs() {
    try {
      const data = (await api.listTasks()) as { tasks: Job[] };
      setJobs(data.tasks);
    } catch {
      // Recent Jobs staying empty/stale is a soft failure — not worth
      // interrupting the user's upload flow over.
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-mount; see https://react.dev/learn/you-might-not-need-an-effect#fetching-data
    refreshJobs();
  }, []);

  async function handleViewResult(jobId: string) {
    setViewingId(jobId);
    try {
      const data = (await api.getTaskResult(jobId)) as { output_file_url: string };
      window.open(data.output_file_url, "_blank");
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Something went wrong.";
      alert(`Could not load result: ${message}`);
    } finally {
      setViewingId(null);
    }
  }

  function handleCategoryChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const nextCategory = e.target.value;
    setCategory(nextCategory);
    setTask(JOB_CATEGORIES[nextCategory][0]);
  }

  function handleLogout() {
    localStorage.removeItem("token");
    localStorage.removeItem("username");
    navigate("/login");
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files?.[0]) setFile(e.target.files[0]);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files?.[0]) setFile(e.dataTransfer.files[0]);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;

    if (!TASK_TYPE[task]) {
      alert(`"${task}" isn't wired up to the backend yet.`);
      return;
    }

    try {
      const { file_key } = await api.upload(file);
      await api.createTask({
        type: "image_resize",
        file_url: file_key,
        width: Number(width),
        height: Number(height),
      });
      setFile(null);
      alert("Job submitted!");
      await refreshJobs();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Something went wrong.";
      alert(`Job submission failed: ${message}`);
    }
  }

  function statusClass(status: string) {
    if (status === "done") return "badge badge-complete";
    if (status === "processing") return "badge badge-running";
    if (status === "failed") return "badge badge-failed";
    return "badge badge-pending";
  }

  return (
    <div className="dash-root">
      {/* Nav */}
      <nav className="dash-nav">
        <span className="dash-logo">ASCEND</span>
        <div className="dash-nav-right">
          <span className="dash-username">{username}</span>
          <button className="dash-logout" onClick={handleLogout}>Logout</button>
        </div>
      </nav>

      <div className="dash-body">
        <aside className="dash-sidebar">
          <nav className="dash-sidebar-nav">
            {SIDEBAR_LINKS.map((link) => (
              <button
                key={link.path}
                className={`dash-sidebar-item ${location.pathname === link.path ? "active" : ""}`}
                onClick={() => navigate(link.path)}
              >
                <span className="dash-sidebar-icon">{link.icon}</span>
                <span>{link.label}</span>
              </button>
            ))}
          </nav>
        </aside>

        <main className="dash-main">
          <div className="dash-stats">
            <div className="dash-stat-card">
              <p className="dash-stat-label">Jobs Run</p>
              <p className="dash-stat-value">{jobs.length}</p>
            </div>
            <div className="dash-stat-card">
              <p className="dash-stat-label">Files Processed</p>
              <p className="dash-stat-value">{jobs.filter((j) => j.status === "done").length}</p>
            </div>
            <div className="dash-stat-card">
              <p className="dash-stat-label">Credits Remaining</p>
              <p className="dash-stat-value">850</p>
            </div>
          </div>

          {/* Upload Card */}
        <section className="dash-card">
          <h2 className="dash-section-title">Upload a File</h2>
          <form onSubmit={handleSubmit}>
            <div
              className={`dash-dropzone ${dragOver ? "dragover" : ""} ${file ? "has-file" : ""}`}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => document.getElementById("file-input")?.click()}
            >
              <input
                id="file-input"
                type="file"
                accept="image/*,video/*"
                style={{ display: "none" }}
                onChange={handleFileChange}
              />
              {file ? (
                <>
                  <div className="dropzone-icon">✅</div>
                  <p className="dropzone-filename">{file.name}</p>
                  <p className="dropzone-hint">Click to change file</p>
                </>
              ) : (
                <>
                  <div className="dropzone-icon">☁️</div>
                  <p className="dropzone-text">Drag & drop or click to upload</p>
                  <p className="dropzone-hint">Supports images and videos</p>
                </>
              )}
            </div>

            <div className="dash-row">
              <div className="dash-field">
                <label className="dash-label">Category</label>
                <select
                  className="dash-select"
                  value={category}
                  onChange={handleCategoryChange}
                >
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>

              <div className="dash-field">
                <label className="dash-label">Task</label>
                <select
                  className="dash-select"
                  value={task}
                  onChange={(e) => setTask(e.target.value)}
                >
                  {JOB_CATEGORIES[category].map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>

              {task === "Image Resize/Upscale" && (
                <>
                  <div className="dash-field">
                    <label className="dash-label">Width</label>
                    <input
                      type="number"
                      className="dash-select"
                      value={width}
                      onChange={(e) => setWidth(e.target.value)}
                    />
                  </div>
                  <div className="dash-field">
                    <label className="dash-label">Height</label>
                    <input
                      type="number"
                      className="dash-select"
                      value={height}
                      onChange={(e) => setHeight(e.target.value)}
                    />
                  </div>
                </>
              )}

              <button
                className="dash-submit"
                type="submit"
                disabled={!file}
              >
                Submit Job
              </button>
            </div>
          </form>
        </section>

        {/* Jobs List */}
        <section className="dash-card">
          <h2 className="dash-section-title">Recent Jobs</h2>
          {jobs.length === 0 ? (
            <p className="dash-empty">No jobs yet. Upload a file to get started.</p>
          ) : (
            <table className="dash-table">
              <thead>
                <tr>
                  <th>File</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Date</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id}>
                    <td className="dash-file">{basename(job.input_key)}</td>
                    <td>{job.job_type}</td>
                    <td><span className={statusClass(job.status)}>{job.status}</span></td>
                    <td className="dash-date">{new Date(job.created_at).toLocaleString()}</td>
                    <td>
                      {job.status === "done" ? (
                        <button
                          className="dash-view-result"
                          onClick={() => handleViewResult(job.id)}
                          disabled={viewingId === job.id}
                        >
                          {viewingId === job.id ? "Loading..." : "View"}
                        </button>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </main>
      </div>
    </div>
  );
}
