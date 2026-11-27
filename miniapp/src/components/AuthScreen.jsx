export function AuthScreen({ error, onEnableDemoMode }) {
  return (
    <main className="auth-screen">
      <div className="auth-card">
        <div className="brand-mark">C</div>
        <p className="eyebrow">CYBERLEARN STUDIO</p>
        <h1>Admin workspace</h1>
        <p>Open this app from the CyberLearn Studio button in your Telegram bot chat.</p>
        {error && <div className="error-box">{error}</div>}
        <p className="muted small" style={{ marginBottom: "var(--space-5)" }}>
          Only Telegram accounts on the configured admin allowlist can sign in directly.
        </p>

        {onEnableDemoMode && (
          <div style={{ borderTop: "1px solid var(--border-soft)", paddingTop: "var(--space-4)" }}>
            <p className="muted small" style={{ marginBottom: "var(--space-3)" }}>
              Testing locally? You can preview the interface, theme system, and editors directly in your browser:
            </p>
            <button
              type="button"
              className="publish-button"
              style={{ width: "100%", justifyContent: "center" }}
              onClick={onEnableDemoMode}
            >
              ✦ Open Browser Preview
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
