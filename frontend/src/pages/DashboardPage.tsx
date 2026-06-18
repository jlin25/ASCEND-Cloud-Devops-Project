import { useState } from "react";
import { useNavigate } from "react-router-dom";
import "./DashboardPage.css";

const MOCK_JOBS = [
  { id: "1", job_type: "Video Edit", input_file_url: "vacation.mp4", status: "complete", created_at: "2026-06-17" },
  { id: "2", job_type: "Photo Edit", input_file_url: "portrait.jpg", status: "running", created_at: "2026-06-18" },
  { id: "3", job_type: "Video Edit", input_file_url: "demo.mov", status: "pending", created_at: "2026-06-18" },
];

const JOB_TYPES = ["Video Edit", "Photo Edit"];

export default function DashboardPage() {
  const navigate = useNavigate();
  const username = localStorage.getItem("username") || "User";

  const [file, setFile] = useState<File | null>(null);
  const [jobType, setJobType] = useState(JOB_TYPES[0]);
  const [dragOver, setDragOver] = useState(false);

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

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    // TODO: connect to POST /tasks when Supabase jobs table is ready
    alert(`Job submitted!\nFile: ${file.name}\nType: ${jobType}`);
    setFile(null);
  }

  function statusClass(status: string) {
    if (status === "complete") return "badge badge-complete";
    if (status === "running") return "badge badge-running";
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

      <main className="dash-main">
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
                <label className="dash-label">Job Type</label>
                <select
                  className="dash-select"
                  value={jobType}
                  onChange={(e) => setJobType(e.target.value)}
                >
                  {JOB_TYPES.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>

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
          {MOCK_JOBS.length === 0 ? (
            <p className="dash-empty">No jobs yet. Upload a file to get started.</p>
          ) : (
            <table className="dash-table">
              <thead>
                <tr>
                  <th>File</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {MOCK_JOBS.map((job) => (
                  <tr key={job.id}>
                    <td className="dash-file">{job.input_file_url}</td>
                    <td>{job.job_type}</td>
                    <td><span className={statusClass(job.status)}>{job.status}</span></td>
                    <td className="dash-date">{job.created_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </main>
    </div>
  );
}
