import { useState } from "react";
import Login from "./Login";
import Dashboard from "./Dashboard";

export default function App() {
  const [username, setUsername] = useState(() =>
    localStorage.getItem("token") ? localStorage.getItem("username") : null,
  );

  function handleLogin(token: string, name: string) {
    localStorage.setItem("token", token);
    localStorage.setItem("username", name);
    setUsername(name);
  }

  function handleLogout() {
    localStorage.removeItem("token");
    localStorage.removeItem("username");
    setUsername(null);
  }

  return username ? (
    <Dashboard username={username} onLogout={handleLogout} />
  ) : (
    <Login onLogin={handleLogin} />
  );
}
