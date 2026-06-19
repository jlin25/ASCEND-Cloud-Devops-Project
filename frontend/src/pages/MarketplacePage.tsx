import { useNavigate, useLocation } from "react-router-dom";
import "./MarketplacePage.css";

const SIDEBAR_LINKS = [
  { icon: "🖥️", label: "Dashboard", path: "/dashboard" },
  { icon: "🛒", label: "Marketplace", path: "/marketplace" },
  { icon: "⚡", label: "My Jobs", path: "/jobs" },
  { icon: "💳", label: "Pricing", path: "/pricing" },
  { icon: "⚙️", label: "Settings", path: "/settings" },
];

const TASK_TEMPLATES = [
  {
    id: "video-upscale",
    name: "Video Upscale",
    description: "Enhance video resolution up to 4K using AI-powered upscaling. Works on any source quality.",
    estimatedTime: "~5 min",
    price: "$2.99",
    icon: "🎬",
    accent: "#38bdf8",
  },
  {
    id: "background-removal",
    name: "Background Removal",
    description: "Cleanly remove or replace backgrounds from images with pixel-perfect edge detection.",
    estimatedTime: "~30 sec",
    price: "$0.49",
    icon: "✂️",
    accent: "#a78bfa",
  },
  {
    id: "ai-voiceover",
    name: "AI Voiceover",
    description: "Generate natural-sounding voiceovers from a script in dozens of voices and languages.",
    estimatedTime: "~2 min",
    price: "$1.99",
    icon: "🎙️",
    accent: "#34d399",
  },
  {
    id: "image-enhancement",
    name: "Image Enhancement",
    description: "Sharpen details, reduce noise, and auto-correct colors to make photos look their best.",
    estimatedTime: "~1 min",
    price: "$0.99",
    icon: "✨",
    accent: "#fbbf24",
  },
  {
    id: "subtitle-generator",
    name: "Subtitle Generator",
    description: "Automatically transcribe and time-stamp subtitles from any video with high accuracy.",
    estimatedTime: "~3 min",
    price: "$1.49",
    icon: "💬",
    accent: "#f472b6",
  },
  {
    id: "format-converter",
    name: "Format Converter",
    description: "Convert between popular video and image formats instantly with lossless quality options.",
    estimatedTime: "~1 min",
    price: "$0.29",
    icon: "🔄",
    accent: "#38bdf8",
  },
];

export default function MarketplacePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const username = localStorage.getItem("username") || "User";

  function handleLogout() {
    localStorage.removeItem("token");
    localStorage.removeItem("username");
    navigate("/login");
  }

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

        <main className="dash-main mkt-main">
          <div className="mkt-header">
            <h1 className="mkt-title">Task Marketplace</h1>
            <p className="mkt-subtitle">Choose a task template to get started instantly.</p>
          </div>

          <div className="mkt-grid">
            {TASK_TEMPLATES.map((task) => (
              <button
                key={task.id}
                className="mkt-card"
                onClick={() => navigate("/dashboard")}
                style={{ "--card-accent": task.accent } as React.CSSProperties}
              >
                <div className="mkt-card-icon">{task.icon}</div>
                <div className="mkt-card-body">
                  <h2 className="mkt-card-name">{task.name}</h2>
                  <p className="mkt-card-desc">{task.description}</p>
                </div>
                <div className="mkt-card-footer">
                  <span className="mkt-card-time">⏱ {task.estimatedTime}</span>
                  <span className="mkt-card-price">{task.price}</span>
                </div>
              </button>
            ))}
          </div>
        </main>
      </div>
    </div>
  );
}
