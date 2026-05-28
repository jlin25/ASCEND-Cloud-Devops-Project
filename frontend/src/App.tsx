import "./App.css";

function App() {
  return (
    <div className="app">
      <nav className="navbar">
        <h2 className="logo">CloudSync</h2>

        <div className="nav-links">
          <a href="#">Home</a>
          <a href="#">Services</a>
          <a href="#">Dashboard</a>
          <a href="#">Contact</a>
        </div>
      </nav>

      <section className="hero">
        <div className="hero-text">
          <p className="tagline">Cloud Computing Platform</p>

          <h1>Deploy, monitor, and scale your apps in the cloud.</h1>

          <p className="description">
            CloudSync helps teams manage cloud storage, virtual machines,
            deployments, and monitoring from one clean dashboard.
          </p>

          <div className="buttons">
            <button className="primary-btn">Get Started</button>
            <button className="secondary-btn">View Services</button>
          </div>
        </div>

        <div className="hero-card">
          <h3>System Status</h3>

          <p className="status online">● All services operational</p>

          <div className="metric">
            <span>CPU Usage</span>
            <strong>42%</strong>
          </div>
          <div className="bar">
            <div className="bar-fill cpu"></div>
          </div>

          <div className="metric">
            <span>Storage Used</span>
            <strong>68%</strong>
          </div>
          <div className="bar">
            <div className="bar-fill storage"></div>
          </div>

          <div className="metric">
            <span>Network Traffic</span>
            <strong>1.8 GB/s</strong>
          </div>
        </div>
      </section>

      <section className="stats">
        <div className="stat-card">
          <h2>99.9%</h2>
          <p>Uptime</p>
        </div>

        <div className="stat-card">
          <h2>24/7</h2>
          <p>Monitoring</p>
        </div>

        <div className="stat-card">
          <h2>3</h2>
          <p>Cloud Regions</p>
        </div>
      </section>

      <section className="services">
        <h2>Cloud Services</h2>

        <div className="service-grid">
          <div className="service-card">
            <h3>Cloud Storage</h3>
            <p>Upload, manage, and access files securely from anywhere.</p>
          </div>

          <div className="service-card">
            <h3>Virtual Machines</h3>
            <p>Create scalable compute instances for apps and workloads.</p>
          </div>

          <div className="service-card">
            <h3>Monitoring</h3>
            <p>Track CPU, memory, storage, and network usage in real time.</p>
          </div>

          <div className="service-card">
            <h3>Security</h3>
            <p>Protect your cloud resources with authentication and access control.</p>
          </div>
        </div>
      </section>
    </div>
  );
}

export default App;