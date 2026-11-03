import { useEffect, useState } from "react";
import { basename, LABELS, parseUtc, timeAgo, type Job } from "./jobs";

type Props = {
  job: Job;
  onDownload: (id: string) => void;
  onDelete: (id: string) => void;
};

export default function JobDetail({ job, onDownload, onDelete }: Props) {
  // Delete is armed by the first click; a second click deletes (it also removes the S3 files).
  const [confirming, setConfirming] = useState(false);

  // Disarm after a few seconds or on any click elsewhere.
  useEffect(() => {
    if (!confirming) return;
    const disarm = () => setConfirming(false);
    const id = setTimeout(disarm, 3000);
    document.addEventListener("click", disarm);
    return () => {
      clearTimeout(id);
      document.removeEventListener("click", disarm);
    };
  }, [confirming]);

  const created = parseUtc(job.created_at);
  const active = job.status === "pending" || job.status === "processing";

  return (
    <section className="card detail">
      <div className="card-head">
        <h1 className="detail-name" title={job.input_key}>
          {basename(job.input_key)}
        </h1>
        <span className={`badge ${job.status}`}>{job.status}</span>
      </div>

      <dl className="detail-grid">
        <dt>Job</dt>
        <dd>{LABELS[job.job_type] ?? job.job_type}</dd>
        <dt>Submitted</dt>
        <dd title={created.toLocaleString()}>{timeAgo(created)}</dd>
        {job.output_key && (
          <>
            <dt>Output</dt>
            <dd className="detail-file">{basename(job.output_key)}</dd>
          </>
        )}
      </dl>

      {active && <p className="muted">Working on it — this updates automatically.</p>}
      {job.status === "failed" && <p className="error">This job failed. Try submitting the file again.</p>}

      <div className="detail-actions">
        {job.status === "done" && (
          <button className="primary" onClick={() => onDownload(job.id)}>
            Download
          </button>
        )}
        <button
          className={`link danger${confirming ? " confirm" : ""}`}
          onClick={(e) => {
            // Keep this click from reaching the document listener that disarms the button.
            e.stopPropagation();
            if (!confirming) return setConfirming(true);
            setConfirming(false);
            onDelete(job.id);
          }}
        >
          {confirming ? "Click again to delete" : "Delete"}
        </button>
      </div>
    </section>
  );
}
