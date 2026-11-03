import { useEffect, useState } from "react";
import { api } from "./api";
import { basename, LABELS, mediaKind, parseUtc, timeAgo, type Job } from "./jobs";

function Preview({ label, url, fileKey, placeholder }: { label: string; url?: string | null; fileKey?: string | null; placeholder: string }) {
  const kind = fileKey ? mediaKind(fileKey) : null;
  let body;
  if (!url || !fileKey) {
    body = <p className="muted">{placeholder}</p>;
  } else if (kind === "image") {
    body = (
      <a href={url} target="_blank" rel="noopener noreferrer" title="Open full size">
        <img src={url} alt={basename(fileKey)} />
      </a>
    );
  } else if (kind === "video") {
    body = <video src={url} controls preload="metadata" />;
  } else {
    body = <p className="muted">No preview for this file type. Download it to view.</p>;
  }
  return (
    <figure className="preview">
      <figcaption className="muted">{label}</figcaption>
      <div className="preview-box">{body}</div>
    </figure>
  );
}

type Props = {
  job: Job;
  onDelete: (id: string) => void;
};

export default function JobDetail({ job, onDelete }: Props) {
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

  // Viewable links for the original and (once done) the result; refetched when the status changes.
  const [files, setFiles] = useState<{ input_url: string; output_url: string | null } | null>(null);
  const [filesError, setFilesError] = useState(false);
  useEffect(() => {
    let cancelled = false;
    api
      .getTaskFiles(job.id)
      .then((data) => !cancelled && setFiles(data))
      .catch(() => !cancelled && setFilesError(true));
    return () => {
      cancelled = true;
    };
  }, [job.id, job.status]);

  const created = parseUtc(job.created_at);
  const active = job.status === "pending" || job.status === "processing";
  const unavailable = filesError ? "Preview unavailable" : "Loading…";

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

      <div className="previews">
        <Preview label="Original" url={files?.input_url} fileKey={job.input_key} placeholder={unavailable} />
        <Preview
          label="Result"
          url={files?.output_url}
          fileKey={job.output_key}
          placeholder={
            job.status === "done" ? unavailable : job.status === "failed" ? "No result" : "Your result will appear here"
          }
        />
      </div>

      {active && <p className="muted">Working on it — this updates automatically.</p>}
      {job.status === "failed" && <p className="error">This job failed. Try submitting the file again.</p>}

      <div className="detail-actions">
        {/* A plain link (not window.open after a fetch) so popup blockers leave it alone. */}
        {job.status === "done" && files?.output_url && (
          <a className="primary button-link" href={files.output_url} target="_blank" rel="noopener noreferrer">
            Open result
          </a>
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
