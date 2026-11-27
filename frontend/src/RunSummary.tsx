import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type Bundle } from "./api";
import { basename, type Job, type Skipped } from "./jobs";

// The most recent folder / multi-file submit.
export type Run = {
  label: string; 
  taskIds: string[];
  skipped: Skipped[];
  failedUploads: Skipped[];
  createdAt: string;
  bundleId?: string;
};

type Props = {
  run: Run;
  jobs: Job[];
  onSelect: (id: string) => void;
  // Stable callbacks (useCallback in Dashboard), so polling isn't restarted on every render.
  onBundleChange: (bundleId: string | undefined) => void;
  onClose: () => void;
  onError: (err: unknown, prefix: string) => void;
};

const STATUSES = [
  ["done", "done"],
  ["processing", "processing"],
  ["pending", "waiting"],
  ["failed", "failed"],
] as const;

export default function RunSummary({ run, jobs, onSelect, onBundleChange, onClose, onError }: Props) {
  const { bundleId } = run;
  const runJobs = run.taskIds.map((id) => jobs.find((j) => j.id === id)).filter((j): j is Job => !!j);
  const inFlight = runJobs.some((j) => j.status === "pending" || j.status === "processing");
  const doneIds = runJobs.filter((j) => j.status === "done").map((j) => j.id);

  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [requesting, setRequesting] = useState(false);
  const zipping = !!bundleId && (!bundle || bundle.status === "pending" || bundle.status === "processing");

  const loadBundle = useCallback(async () => {
    if (!bundleId) return;
    try {
      setBundle(await api.getBundle(bundleId));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setBundle(null);
        onBundleChange(undefined);
      } else onError(err, "Couldn't check the ZIP");
    }
  }, [bundleId, onBundleChange, onError]);

  useEffect(() => {
    loadBundle();
  }, [loadBundle]);
  useEffect(() => {
    if (!zipping) return;
    const id = setInterval(loadBundle, 2000);
    return () => clearInterval(id);
  }, [zipping, loadBundle]);

  async function makeZip() {
    setRequesting(true);
    try {
      const { bundle_id } = await api.createBundle(doneIds);
      setBundle(null);
      onBundleChange(bundle_id);
    } catch (err) {
      onError(err, "Couldn't start the ZIP");
    } finally {
      setRequesting(false);
    }
  }

  function close() {
    if (bundleId) api.deleteBundle(bundleId).catch(() => {});
    onClose();
  }

  const pct = bundle?.status === "processing" && bundle.progress ? bundle.progress : null;

  return (
    <section className="card run">
      <div className="card-head">
        <h2 className="run-title">Last run: {run.label}</h2>
        <button className="link close-button" onClick={close} aria-label="Close" title="Close">
          ×
        </button>
      </div>

      <p className="run-counts">
        {STATUSES.map(([status, label]) => {
          const n = runJobs.filter((j) => j.status === status).length;
          return n ? (
            <span key={status} className={`badge ${status}`}>
              {n} {label}
            </span>
          ) : null;
        })}
        {runJobs.length === 0 && <span className="muted">No jobs left from this run.</span>}
      </p>

      {run.failedUploads.length > 0 && <SkipList title="Upload failed" items={run.failedUploads} error />}
      {run.skipped.length > 0 && <SkipList title="Skipped" items={run.skipped} />}

      {runJobs.length > 0 && (
        <details className="run-files">
          <summary>Files ({runJobs.length})</summary>
          <ul className="run-list">
            {runJobs.map((job) => (
              <li key={job.id}>
                <button className="run-file" onClick={() => onSelect(job.id)}>
                  <span className={`dot ${job.status}`} />
                  <span className="side-name">{basename(job.input_key)}</span>
                  <span className="muted">{job.status === "pending" ? "waiting" : job.status}</span>
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="detail-actions run-actions">
        {zipping ? (
          <div className="progress-wrap run-zip">
            <div
              className={`progress${pct === null ? " indeterminate" : ""}`}
              role="progressbar"
              aria-label="ZIP progress"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={pct ?? undefined}
            >
              <div className="progress-fill" style={pct !== null ? { width: `${pct}%` } : undefined} />
            </div>
            <p className="muted progress-label">{pct !== null ? `Preparing ZIP · ${pct}%` : "Preparing ZIP…"}</p>
          </div>
        ) : bundle?.status === "done" && bundle.download_url ? (
          // A plain link (not window.open after a fetch) so popup blockers leave it alone.
          <a className="primary button-link" href={bundle.download_url}>
            Download ZIP
          </a>
        ) : (
          <>
            {bundle?.status === "failed" && <span className="error">Couldn't build the ZIP. Try again.</span>}
            <button
              className="primary"
              onClick={makeZip}
              disabled={inFlight || doneIds.length === 0 || requesting}
              title={inFlight ? "Available once every file has finished" : undefined}
            >
              {requesting ? "Starting…" : "Download all as ZIP"}
            </button>
          </>
        )}
      </div>
    </section>
  );
}

function SkipList({ title, items, error }: { title: string; items: Skipped[]; error?: boolean }) {
  return (
    <details className="run-files">
      <summary className={error ? "error" : "muted"}>
        {title} ({items.length})
      </summary>
      <ul className="run-list">
        {items.map((s, i) => (
          <li key={i} className="run-skip">
            <span className="side-name">{s.name}</span>
            <span className="muted">{s.reason}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}
