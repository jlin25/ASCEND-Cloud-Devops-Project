import { useEffect, useState } from "react";
import { basename, LABELS, parseUtc, type Job } from "./jobs";

function initials(name: string) {
  const parts = name.split(/[\s._-]+/).filter(Boolean);
  const letters = parts.length > 1 ? parts[0][0] + parts[1][0] : name.slice(0, 2);
  return (letters || "?").toUpperCase();
}

// Stable per-user colour so the avatar is recognisable at a glance.
function avatarColor(name: string) {
  let hash = 0;
  for (const ch of name) hash = (hash * 31 + ch.charCodeAt(0)) | 0;
  return `hsl(${Math.abs(hash) % 360} 55% 45%)`;
}

type Props = {
  username: string;
  jobs: Job[];
  selectedId: string | null;
  open: boolean;
  onSelect: (id: string | null) => void;
  onRefresh: () => void;
  onLogout: () => void;
};

export default function Sidebar({ username, jobs, selectedId, open, onSelect, onRefresh, onLogout }: Props) {
  const [menuOpen, setMenuOpen] = useState(false);

  // Close the user menu on any click outside it.
  useEffect(() => {
    if (!menuOpen) return;
    const close = () => setMenuOpen(false);
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, [menuOpen]);

  return (
    <aside className={`sidebar${open ? " open" : ""}`}>
      <div className="sidebar-head">
        <span className="logo">ASCEND</span>
      </div>

      <button className={`side-item new${selectedId === null ? " active" : ""}`} onClick={() => onSelect(null)}>
        <span className="side-icon">+</span>
        New job
      </button>

      <div className="side-label">
        <span>Uploads</span>
        <button className="link" onClick={onRefresh} title="Refresh">
          ↻
        </button>
      </div>

      <nav className="side-list">
        {jobs.length === 0 ? (
          <p className="muted side-empty">No uploads yet</p>
        ) : (
          jobs.map((job) => (
            <button
              key={job.id}
              className={`side-item${job.id === selectedId ? " active" : ""}`}
              onClick={() => onSelect(job.id)}
              title={`${LABELS[job.job_type] ?? job.job_type} · ${job.status} · ${parseUtc(job.created_at).toLocaleString()}`}
            >
              <span className={`dot ${job.status}`} />
              <span className="side-name">{basename(job.input_key)}</span>
            </button>
          ))
        )}
      </nav>

      <div className="user">
        {menuOpen && (
          <div className="user-menu">
            <button className="side-item" onClick={onLogout}>
              Log out
            </button>
          </div>
        )}
        <button
          className="side-item"
          onClick={(e) => {
            // Keep this click from reaching the document listener that closes the menu.
            e.stopPropagation();
            setMenuOpen(!menuOpen);
          }}
        >
          <span className="avatar" style={{ background: avatarColor(username) }}>
            {initials(username)}
          </span>
          <span className="side-name">{username}</span>
        </button>
      </div>
    </aside>
  );
}
