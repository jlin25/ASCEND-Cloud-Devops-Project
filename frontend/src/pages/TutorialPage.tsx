import { useState } from "react";
import { useNavigate } from "react-router-dom";
import "./TutorialPage.css";

interface Step {
  title: string;
  content: React.ReactNode;
}

interface Chapter {
  id: string;
  icon: string;
  title: string;
  steps: Step[];
}

const chapters: Chapter[] = [
  {
    id: "getting-started",
    icon: "🚀",
    title: "Getting Started",
    steps: [
      {
        title: "What is ASCEND?",
        content: (
          <>
            <p>
              ASCEND is a cloud-based task execution marketplace. It lets you
              run compute-intensive jobs — machine learning, data processing,
              rendering — without managing any infrastructure.
            </p>
            <div className="info-box">
              <strong>Key benefits:</strong>
              <ul>
                <li>No server setup — just submit a task and go</li>
                <li>Auto-scaling compute that matches your workload</li>
                <li>Pay only for what you use</li>
              </ul>
            </div>
          </>
        ),
      },
      {
        title: "Create your account",
        content: (
          <>
            <p>
              Click <strong>Get Started</strong> on the homepage to create a
              free account. You'll need an email address and a password.
            </p>
            <div className="step-callout">
              <span className="callout-icon">💡</span>
              <span>
                Free accounts include <strong>10 compute hours</strong> per
                month and <strong>5 GB</strong> of cloud storage.
              </span>
            </div>
          </>
        ),
      },
    ],
  },
  {
    id: "submit-task",
    icon: "⚡",
    title: "Submit a Task",
    steps: [
      {
        title: "Describe your task",
        content: (
          <>
            <p>
              From the homepage, type what you want to run in the input bar. Be
              as specific as possible.
            </p>
            <div className="code-block">
              <span className="code-label">Example prompt</span>
              <code>
                Train a ResNet-50 model on my dataset.csv with 50 epochs
              </code>
            </div>
            <p>
              ASCEND will automatically select the right compute type (CPU, GPU,
              or TPU) based on your task.
            </p>
          </>
        ),
      },
      {
        title: "Use quick actions",
        content: (
          <>
            <p>
              Not sure what to type? Click one of the <strong>quick action cards</strong>{" "}
              on the homepage:
            </p>
            <div className="action-list">
              <div className="action-item">
                <span>⚡</span>
                <div>
                  <strong>Deploy a VM</strong> — spin up a virtual machine in
                  seconds
                </div>
              </div>
              <div className="action-item">
                <span>🤖</span>
                <div>
                  <strong>Run ML Job</strong> — submit a training or inference
                  job
                </div>
              </div>
              <div className="action-item">
                <span>☁️</span>
                <div>
                  <strong>Upload Files</strong> — store data in cloud storage
                </div>
              </div>
              <div className="action-item">
                <span>📊</span>
                <div>
                  <strong>Monitor Usage</strong> — check your resource metrics
                </div>
              </div>
            </div>
          </>
        ),
      },
      {
        title: "Track your job",
        content: (
          <>
            <p>
              After submitting, you're taken to the <strong>Job Dashboard</strong>.
              Each job shows:
            </p>
            <div className="status-grid">
              <div className="status-pill pending">● Queued</div>
              <div className="status-pill running">● Running</div>
              <div className="status-pill done">● Complete</div>
              <div className="status-pill error">● Failed</div>
            </div>
            <p>
              You'll receive a notification when your job finishes. Results and
              logs are available for 30 days.
            </p>
          </>
        ),
      },
    ],
  },
  {
    id: "cloud-storage",
    icon: "☁️",
    title: "Cloud Storage",
    steps: [
      {
        title: "Upload files",
        content: (
          <>
            <p>
              Navigate to <strong>Storage</strong> in the dashboard sidebar.
              Drag and drop files or click <strong>Upload</strong>.
            </p>
            <div className="info-box">
              <strong>Supported file types:</strong> CSV, JSON, Parquet, PNG,
              JPG, ZIP, tar.gz, and most common formats. Max single file: 10 GB.
            </div>
          </>
        ),
      },
      {
        title: "Reference files in tasks",
        content: (
          <>
            <p>
              Once uploaded, each file gets a unique path you can reference in
              your tasks:
            </p>
            <div className="code-block">
              <span className="code-label">File path</span>
              <code>ascend://storage/your-username/dataset.csv</code>
            </div>
          </>
        ),
      },
    ],
  },
  {
    id: "monitoring",
    icon: "📊",
    title: "Monitoring",
    steps: [
      {
        title: "View resource metrics",
        content: (
          <>
            <p>
              The <strong>Monitoring</strong> tab shows real-time usage across
              all your resources:
            </p>
            <div className="metric-demo">
              <div className="metric-row">
                <span>CPU Usage</span>
                <div className="demo-bar">
                  <div className="demo-fill" style={{ width: "42%", background: "#38bdf8" }} />
                </div>
                <span>42%</span>
              </div>
              <div className="metric-row">
                <span>Storage</span>
                <div className="demo-bar">
                  <div className="demo-fill" style={{ width: "68%", background: "#818cf8" }} />
                </div>
                <span>68%</span>
              </div>
              <div className="metric-row">
                <span>Network</span>
                <div className="demo-bar">
                  <div className="demo-fill" style={{ width: "30%", background: "#22c55e" }} />
                </div>
                <span>1.8 GB/s</span>
              </div>
            </div>
          </>
        ),
      },
      {
        title: "Set up alerts",
        content: (
          <>
            <p>
              Go to <strong>Settings → Alerts</strong> to create threshold
              alerts. You'll be notified by email or webhook when a metric
              exceeds your limit.
            </p>
            <div className="step-callout">
              <span className="callout-icon">⚠️</span>
              <span>
                Recommended: set a <strong>budget alert</strong> to avoid
                unexpected charges.
              </span>
            </div>
          </>
        ),
      },
    ],
  },
];

export default function TutorialPage() {
  const [activeChapter, setActiveChapter] = useState(chapters[0].id);
  const [activeStep, setActiveStep] = useState(0);
  const navigate = useNavigate();

  const chapter = chapters.find((c) => c.id === activeChapter)!;
  const totalSteps = chapter.steps.length;
  const step = chapter.steps[activeStep];

  function goNext() {
    if (activeStep < totalSteps - 1) {
      setActiveStep(activeStep + 1);
    } else {
      const idx = chapters.findIndex((c) => c.id === activeChapter);
      if (idx < chapters.length - 1) {
        setActiveChapter(chapters[idx + 1].id);
        setActiveStep(0);
      }
    }
  }

  function goPrev() {
    if (activeStep > 0) {
      setActiveStep(activeStep - 1);
    } else {
      const idx = chapters.findIndex((c) => c.id === activeChapter);
      if (idx > 0) {
        const prev = chapters[idx - 1];
        setActiveChapter(prev.id);
        setActiveStep(prev.steps.length - 1);
      }
    }
  }

  const isFirst =
    chapters.findIndex((c) => c.id === activeChapter) === 0 && activeStep === 0;
  const isLast =
    chapters.findIndex((c) => c.id === activeChapter) === chapters.length - 1 &&
    activeStep === totalSteps - 1;

  return (
    <div className="tut-root">
      {/* Top bar */}
      <nav className="tut-nav">
        <button className="tut-back-btn" onClick={() => navigate("/")}>
          ← Home
        </button>
        <span className="tut-nav-title">ASCEND Tutorial Guide</span>
        <span className="tut-nav-version">v1.0</span>
      </nav>

      <div className="tut-layout">
        {/* Sidebar */}
        <aside className="tut-sidebar">
          <p className="sidebar-label">Chapters</p>
          {chapters.map((ch) => (
            <button
              key={ch.id}
              className={`sidebar-item ${activeChapter === ch.id ? "active" : ""}`}
              onClick={() => {
                setActiveChapter(ch.id);
                setActiveStep(0);
              }}
            >
              <span className="sidebar-icon">{ch.icon}</span>
              <span>{ch.title}</span>
            </button>
          ))}

          <div className="sidebar-divider" />

          <div className="sidebar-progress">
            <p className="sidebar-label">Progress</p>
            {chapters.map((ch) => (
              <div key={ch.id} className="progress-row">
                <span
                  className={`progress-dot ${activeChapter === ch.id ? "active" : ""}`}
                />
                <span className="progress-name">{ch.title}</span>
              </div>
            ))}
          </div>
        </aside>

        {/* Main content */}
        <main className="tut-content">
          <div className="tut-breadcrumb">
            {chapter.icon} {chapter.title}
          </div>

          <div className="tut-step-header">
            <span className="step-badge">
              Step {activeStep + 1} of {totalSteps}
            </span>
            <h2 className="tut-step-title">{step.title}</h2>
          </div>

          <div className="tut-step-body">{step.content}</div>

          {/* Navigation */}
          <div className="tut-nav-btns">
            <button
              className="tut-btn secondary"
              onClick={goPrev}
              disabled={isFirst}
            >
              ← Previous
            </button>
            {isLast ? (
              <button
                className="tut-btn primary"
                onClick={() => navigate("/")}
              >
                Finish & Go Home ✓
              </button>
            ) : (
              <button className="tut-btn primary" onClick={goNext}>
                Next →
              </button>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
