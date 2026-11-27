import React, { Component } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import { ThemeProvider } from "./ThemeContext.jsx";
import "./styles.css";

function initTelegram() {
  try {
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready();
      tg.expand();
      if (typeof tg.requestFullscreen === "function") {
        try { tg.requestFullscreen(); } catch (e) {}
      }
      try {
        const stored = localStorage.getItem("cyberlearn-theme");
        const bg = stored === "light" ? "#f3efe6" : "#090910";
        if (typeof tg.setHeaderColor === "function") tg.setHeaderColor(bg);
        if (typeof tg.setBackgroundColor === "function") tg.setBackgroundColor(bg);
      } catch (e) {}
      if (typeof tg.disableVerticalSwipes === "function") {
        tg.disableVerticalSwipes();
        if (typeof tg.onEvent === "function") {
          tg.onEvent("viewportChanged", () => {
            try { tg.disableVerticalSwipes(); } catch(e) {}
          });
        }
      }
      if (tg.BackButton) {
        tg.BackButton.hide();
      }
      return true;
    }
  } catch (e) {
    // Ignore Telegram WebApp initialisation errors in normal browsers
  }
  return false;
}

initTelegram();
if (typeof window !== "undefined") {
  window.addEventListener("DOMContentLoaded", initTelegram);
  setTimeout(initTelegram, 50);
  setTimeout(initTelegram, 250);
}

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("Studio render error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="auth-screen">
          <div className="auth-card" style={{ maxWidth: 500, textAlign: "center" }}>
            <div className="brand-mark" style={{ margin: "0 auto var(--space-4)" }}>C</div>
            <p className="eyebrow">CYBERLEARN STUDIO</p>
            <h1>Application Notice</h1>
            <p className="muted" style={{ marginBottom: "var(--space-4)" }}>
              {this.state.error?.message || "An unexpected error occurred during rendering."}
            </p>
            <div style={{ display: "flex", gap: "var(--space-2)", justifyContent: "center" }}>
              <button
                type="button"
                className="publish-button"
                onClick={() => {
                  window.localStorage.removeItem("cyberlearn-theme");
                  window.location.reload();
                }}
              >
                Reload Studio
              </button>
            </div>
          </div>
        </main>
      );
    }
    return this.props.children;
  }
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ErrorBoundary>
      <ThemeProvider initialTheme="dark">
        <App />
      </ThemeProvider>
    </ErrorBoundary>
  </React.StrictMode>,
);
