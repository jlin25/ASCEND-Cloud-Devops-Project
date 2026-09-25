import { useNavigate } from "react-router-dom";
import "./NotFoundPage.css";

export default function NotFoundPage() {
  const navigate = useNavigate();

  return (
    <div className="notfound-root">
      <div className="notfound-icon">☁️</div>
      <h1 className="notfound-title">Page not found</h1>
      <p className="notfound-sub">This page doesn't exist yet or hasn't been built.</p>
      <button className="notfound-home-btn" onClick={() => navigate("/")}>
        ← Back to Home
      </button>
    </div>
  );
}
