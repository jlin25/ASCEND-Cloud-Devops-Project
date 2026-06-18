import { useState } from "react";
import { useNavigate } from "react-router-dom";
import "./HomePage.css";

const suggestions = [
  { icon: "⚡", label: "Deploy a VM", prompt: "Deploy a new virtual machine" },
  { icon: "🤖", label: "Run ML Job", prompt: "Run a machine learning training job" },
  { icon: "☁️", label: "Upload Files", prompt: "Upload files to cloud storage" },
  { icon: "📊", label: "Monitor Usage", prompt: "Show my cloud resource usage" },
];

export default function HomePage() {
  const [input, setInput] = useState("");
  const navigate = useNavigate();

  function handleSuggestion(prompt: string) {
    setInput(prompt);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim()) return;
    // Placeholder: route to dashboard or job submission
    alert(`Submitting task: "${input}"\n\n(Dashboard coming soon!)`);
    setInput("");
  }

  return (
    <div className="home-root">
      {/* Top nav */}
      <nav className="home-nav">
        <span className="home-logo">ASCEND</span>
        <div className="home-nav-right">
          <button
            className="nav-link-btn"
            onClick={() => navigate("/tutorial")}
          >
            Tutorial
          </button>
          <button className="nav-link-btn">Docs</button>
          <button className="nav-cta" onClick={() => navigate("/login")}>Get Started</button>
        </div>
      </nav>

      {/* Main centered content */}
      <main className="home-main">
        <div className="home-center">
          <div className="home-icon">☁️</div>
          <h1 className="home-heading">What would you like to run today?</h1>
          <p className="home-subheading">
            Submit a cloud task or pick a quick action below
          </p>

          {/* Suggestion cards */}
          <div className="suggestion-grid">
            {suggestions.map((s) => (
              <button
                key={s.label}
                className="suggestion-card"
                onClick={() => handleSuggestion(s.prompt)}
              >
                <span className="suggestion-icon">{s.icon}</span>
                <span className="suggestion-label">{s.label}</span>
              </button>
            ))}
          </div>

          {/* Input box */}
          <form className="home-input-wrap" onSubmit={handleSubmit}>
            <input
              className="home-input"
              type="text"
              placeholder="Describe your cloud task..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              autoFocus
            />
            <button
              type="submit"
              className="home-send-btn"
              disabled={!input.trim()}
              aria-label="Submit"
            >
              ➤
            </button>
          </form>

          <p className="home-hint">
            New to ASCEND?{" "}
            <button
              className="home-hint-link"
              onClick={() => navigate("/tutorial")}
            >
              View the tutorial guide →
            </button>
          </p>
        </div>
      </main>

      {/* Footer */}
      <footer className="home-footer">
        <span>© 2026 ASCEND Cloud</span>
        <span>99.9% Uptime · 3 Regions · 24/7 Monitoring</span>
      </footer>
    </div>
  );
}
