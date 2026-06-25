import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import "./JobsPage.css";

const SIDEBAR_LINKS = [
  { icon: "🖥️", label: "Dashboard", path: "/dashboard" },
  { icon: "🛒", label: "Marketplace", path: "/marketplace" },
  { icon: "⚡", label: "My Jobs", path: "/jobs" },
  { icon: "💳", label: "Pricing", path: "/pricing" },
  { icon: "⚙️", label: "Settings", path: "/settings" },
];

type JobStatus = "queued" | "running" | "complete" | "failed";

interface Job {
  id: string;
  job_name: string;
  file_name: string;
  status: JobStatus;
  submitted_at: string;
  download_url: string | null;
}

// TODO: Replace with Supabase query — `supabase.from('jobs').select('*').eq('user_id', userId).order('submitted_at', { ascending: false })`
const MOCK_JOBS: Job[] = [
  {
    id: "1",
    job_name: "Video Upscale",
    file_name: "vacation.mp4",
    status: "complete",
    submitted_at: "2026-06-17",
    download_url: "#", // TODO: Replace with signed Supabase Storage URL
  },
  {
    id: "2",
    job_name: "Background Removal",
    file_name: "portrait.jpg",
    status: "running",
    submitted_at: "2026-06-18",
    download_url: null,
  },
  {
    id: "3",
    job_name: "Subtitle Generator",
    file_name: "demo.mov",
    status: "queued",
    submitted_at: "2026-06-18",
    download_url: null,
  },
  {
    id: "4",
    job_name: "Image Enhancement",
    file_name: "headshot.png",
    status: "complete",
    submitted_at: "2026-06-16",
    download_url: "#", // TODO: Replace with signed Supabase Storage URL
  },
  {
    id: "5",
    job_name: "AI Voiceover",
    file_name: "script.txt",
    status: "failed",
    submitted_at: "2026-06-15",
    download_url: null,
  },
  {
    id: "6",
    job_name: "Format Converter",
    file_name: "clip.avi",
    status: "complete",
    submitted_at: "2026-06-14",
    download_url: "#", // TODO: Replace with signed Supabase Storage URL
  },
];

const FILTER_OPTIONS: { label: string; value: JobStatus | "all" }[] = [
  { label: "All", value: "all" },
  { label: "Queued", value: "queued" },
  { label: "Running", value: "running" },
  { label: "Complete", value: "complete" },
  { label: "Failed", value: "failed" },
];

function statusBadgeClass(status: JobStatus): string {
  if (status === "complete") return "badge badge-complete";
  if (status === "running") return "badge badge-running";
  if (status === "failed") return "badge badge-failed";
  return "badge badge-queued";
}

export default function JobsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const username = localStorage.getItem("username") || "User";

  const [activeFilter, setActiveFilter] = useState<JobStatus | "all">("all");

  function handleLogout() {
    localStorage.removeItem("token");
    localStorage.removeItem("username");
    navigate("/login");
  }

  // TODO: Replace MOCK_JOBS with live Supabase data; filtering can remain client-side or move to a query param
  const filteredJobs =
    activeFilter === "all"
      ? MOCK_JOBS
      : MOCK_JOBS.filter((j) => j.status === activeFilter);

  return (
    <div className="dash-root">
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
          <section className="dash-card">
            <div className="jobs-header">
              <h2 className="dash-section-title" style={{ margin: 0 }}>My Jobs</h2>
              <div className="jobs-filters">
                {FILTER_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    className={`jobs-filter-btn ${activeFilter === opt.value ? "jobs-filter-active" : ""}`}
                    onClick={() => setActiveFilter(opt.value)}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            {filteredJobs.length === 0 ? (
              <div className="jobs-empty">
                <div className="jobs-empty-icon">📭</div>
                <p className="jobs-empty-title">No jobs found</p>
                <p className="jobs-empty-sub">
                  {activeFilter === "all"
                    ? "You haven't submitted any jobs yet."
                    : `No jobs with status "${activeFilter}".`}
                </p>
                {activeFilter !== "all" && (
                  <button
                    className="jobs-empty-reset"
                    onClick={() => setActiveFilter("all")}
                  >
                    Show all jobs
                  </button>
                )}
              </div>
            ) : (
              <table className="dash-table jobs-table">
                <thead>
                  <tr>
                    <th>Status</th>
                    <th>Job</th>
                    <th>File</th>
                    <th>Submitted</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {filteredJobs.map((job) => (
                    <tr key={job.id}>
                      <td>
                        <span className={statusBadgeClass(job.status)}>
                          {job.status}
                        </span>
                      </td>
                      <td className="jobs-job-name">{job.job_name}</td>
                      <td className="dash-file">{job.file_name}</td>
                      <td className="dash-date">{job.submitted_at}</td>
                      <td className="jobs-action-cell">
                        {job.status === "complete" && job.download_url ? (
                          // TODO: Replace href with signed Supabase Storage URL from `supabase.storage.from('outputs').createSignedUrl(...)`
                          <a
                            className="jobs-download-btn"
                            href={job.download_url}
                            download
                          >
                            ↓ Download
                          </a>
                        ) : null}
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
