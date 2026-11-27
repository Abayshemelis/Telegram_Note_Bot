import { useCallback, useContext, useEffect, useState } from "react";
import ThemeContext from "../ThemeContext";

const DEFAULT_SETTINGS = {
  channel_id: "",
  channel_title: "",
  delivery_mode: "card",
  post_header_style: "academic",
  branding_signature: "CyberLearn Academic Team",
  require_approval: true,
  quiz_anonymous: true,
  quiz_default_duration: 10,
  quiz_pass_percentage: 70,
  autosave_enabled: true,
  autosave_interval: 2,
  ai_provider: "groq",
  ai_provider_api_key: "",
  ai_provider_url: "https://api.groq.com/openai/v1/chat/completions",
  ai_provider_model: "openai/gpt-oss-120b",
  groq_api_key: "",
  groq_model: "openai/gpt-oss-120b",
  groq_has_key: false,
  gemini_api_key: "",
  gemini_model: "gemini-3-flash-preview",
  gemini_has_key: false,
  grok_api_key: "",
  grok_model: "grok-2-latest",
  grok_has_key: false,
};

function resolveModelForProvider(provider, currentModel) {
  const p = (provider || "groq").toLowerCase();
  const m = (currentModel || "").trim();
  if (p === "groq") {
    if (!m || m === "gpt-4o" || m.startsWith("gemini") || m.startsWith("grok") || m.includes("llama")) {
      return "openai/gpt-oss-120b";
    }
    return m;
  }
  if (p === "gemini") {
    if (!m || m.startsWith("llama") || m.startsWith("grok") || m === "gpt-4o" || m.includes("gemini-2.5") || m.includes("gemini-1.5")) {
      return "gemini-3-flash-preview";
    }
    return m;
  }
  if (p === "grok") {
    if (!m || m.startsWith("llama") || m.startsWith("gemini") || m === "gpt-4o") {
      return "grok-2-latest";
    }
    return m;
  }
  return m || "gpt-4o";
}

export function SettingsPage({ admin, busy }) {
  const { theme, resolvedTheme, setTheme } = useContext(ThemeContext);
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [initialSettings, setInitialSettings] = useState(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showGroqKey, setShowGroqKey] = useState(false);
  const [showGeminiKey, setShowGeminiKey] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [channelInput, setChannelInput] = useState("");
  const [channelVerifyState, setChannelVerifyState] = useState({
    loading: false,
    ok: null,
    message: "",
    is_admin: null,
  });
  const [aiTestState, setAiTestState] = useState({
    loading: false,
    ok: null,
    message: "",
  });
  const [groqTestState, setGroqTestState] = useState({
    loading: false,
    ok: null,
    message: "",
  });
  const [geminiTestState, setGeminiTestState] = useState({
    loading: false,
    ok: null,
    message: "",
  });
  const [fetchedModels, setFetchedModels] = useState([]);
  const [groqFetchedModels, setGroqFetchedModels] = useState([]);
  const [geminiFetchedModels, setGeminiFetchedModels] = useState([]);
  const [fetchingModels, setFetchingModels] = useState(false);
  const [customModelMode, setCustomModelMode] = useState(false);
  const [groqCustomModelMode, setGroqCustomModelMode] = useState(false);
  const [geminiCustomModelMode, setGeminiCustomModelMode] = useState(false);
  const [savedNotice, setSavedNotice] = useState("");
  const [errorNotice, setErrorNotice] = useState("");
  const [auditLogs, setAuditLogs] = useState([]);
  const [loadingAudit, setLoadingAudit] = useState(false);

  const isDirty = JSON.stringify(settings) !== JSON.stringify(initialSettings);

  const loadSettings = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/settings", {
        headers: {
          "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "",
        },
      });
      if (res.ok) {
        const data = await res.json();
        const prov = data.ai_provider || "groq";
        const groqKey = data.groq_api_key || (data.ai_provider_api_key?.startsWith("gsk_") ? data.ai_provider_api_key : "") || "";
        const geminiKey = data.gemini_api_key || (data.ai_provider_api_key?.startsWith("AQ.") || data.ai_provider_api_key?.startsWith("AIzaSy") ? data.ai_provider_api_key : "") || "";
        const groqModel = data.groq_model || "openai/gpt-oss-120b";
        const geminiModel = data.gemini_model || "gemini-3.8-flash";
        const cleanModel = resolveModelForProvider(prov, prov === "gemini" ? geminiModel : groqModel);
        
        const resolved = {
          ...data,
          ai_provider: prov,
          ai_provider_model: cleanModel,
          groq_api_key: groqKey,
          groq_has_key: Boolean(groqKey),
          groq_model: groqModel,
          gemini_api_key: geminiKey,
          gemini_has_key: Boolean(geminiKey),
          gemini_model: geminiModel,
          ai_provider_api_key: prov === "gemini" ? geminiKey : groqKey,
        };
        setSettings(resolved);
        setInitialSettings(resolved);
        setChannelInput(data.channel_id || data.channel_title || "");
      }
    } catch (e) {
      setErrorNotice("Could not load studio settings.");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadAuditLogs = useCallback(async () => {
    setLoadingAudit(true);
    try {
      const res = await fetch("/api/audit?limit=25", {
        headers: {
          "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "",
        },
      });
      if (res.ok) {
        const data = await res.json();
        setAuditLogs(data);
      }
    } catch (e) {
      // ignore
    } finally {
      setLoadingAudit(false);
    }
  }, []);

  useEffect(() => {
    loadSettings();
    loadAuditLogs();
  }, [loadSettings, loadAuditLogs]);

  const verifyChannel = async () => {
    const target = channelInput.trim();
    if (!target) {
      setChannelVerifyState({
        loading: false,
        ok: false,
        message: "Please enter a channel username (e.g. @mychannel) or numeric ID (-100...)",
        is_admin: false,
      });
      return;
    }

    setChannelVerifyState({
      loading: true,
      ok: null,
      message: "Verifying Telegram channel permissions…",
      is_admin: null,
    });

    try {
      const res = await fetch("/api/settings/verify-channel", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "",
        },
        body: JSON.stringify({ channel: target }),
      });
      const data = await res.json();
      if (!res.ok) {
        setChannelVerifyState({
          loading: false,
          ok: false,
          message: data.detail || "Could not connect to that channel.",
          is_admin: false,
        });
        return;
      }

      setChannelVerifyState({
        loading: false,
        ok: true,
        message: `Connected to "${data.title}" (ID: ${data.id})`,
        is_admin: data.is_admin,
      });

      setSettings((prev) => ({
        ...prev,
        channel_id: data.id,
        channel_title: data.title,
      }));
    } catch (err) {
      setChannelVerifyState({
        loading: false,
        ok: false,
        message: err.message || "Failed to verify channel.",
        is_admin: false,
      });
    }
  };

  const handleUnlinkChannel = () => {
    setSettings((prev) => ({
      ...prev,
      channel_id: "",
      channel_title: "",
    }));
    setChannelInput("");
    setChannelVerifyState({
      loading: false,
      ok: null,
      message: "Channel unlinked. Enter a new channel or leave blank.",
      is_admin: null,
    });
  };

  const selectAiProvider = (provider) => {
    setFetchedModels([]);
    setCustomModelMode(false);
    setSettings((prev) => {
      let activeKey = prev.ai_provider_api_key;
      let activeModel = prev.ai_provider_model;
      let activeUrl = prev.ai_provider_url;

      if (provider === "groq") {
        activeKey = prev.groq_api_key || (prev.ai_provider_api_key?.startsWith("gsk_") ? prev.ai_provider_api_key : "");
        activeModel = prev.groq_model || "openai/gpt-oss-120b";
        activeUrl = "https://api.groq.com/openai/v1/chat/completions";
      } else if (provider === "gemini") {
        activeKey = prev.gemini_api_key || (prev.ai_provider_api_key?.startsWith("AQ.") || prev.ai_provider_api_key?.startsWith("AIzaSy") ? prev.ai_provider_api_key : "");
        activeModel = prev.gemini_model || "gemini-3.8-flash";
        activeUrl = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions";
      } else if (provider === "grok") {
        activeKey = prev.grok_api_key || (prev.ai_provider_api_key?.startsWith("xai-") ? prev.ai_provider_api_key : "");
        activeModel = prev.grok_model || "grok-2-latest";
        activeUrl = "https://api.x.ai/v1/chat/completions";
      } else {
        activeUrl = prev.ai_provider_url || "https://api.openai.com/v1/chat/completions";
        activeModel = "gpt-4o";
      }

      return {
        ...prev,
        ai_provider: provider,
        ai_provider_api_key: activeKey,
        ai_provider_model: activeModel,
        ai_provider_url: activeUrl,
      };
    });
    setAiTestState({ loading: false, ok: null, message: "" });
  };

  const testProvider = async (targetProvider) => {
    const isGroq = targetProvider === "groq";
    const apiKey = isGroq ? settings.groq_api_key : settings.gemini_api_key;
    const model = isGroq
      ? (settings.groq_model || "openai/gpt-oss-120b")
      : (settings.gemini_model || "gemini-3-flash-preview");
    const setTestState = isGroq ? setGroqTestState : setGeminiTestState;

    if (!apiKey?.trim()) {
      setTestState({
        loading: false,
        ok: false,
        message: `Please enter a ${isGroq ? "Groq" : "Gemini"} API key first.`,
      });
      return;
    }

    setTestState({
      loading: true,
      ok: null,
      message: `Connecting to ${isGroq ? "Groq Cloud" : "Google Gemini"} (${model})…`,
    });

    try {
      const res = await fetch("/api/settings/test-ai", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "",
        },
        body: JSON.stringify({
          ai_provider: targetProvider,
          ai_provider_api_key: apiKey.trim(),
          ai_provider_model: model,
          ai_provider_url: isGroq
            ? "https://api.groq.com/openai/v1/chat/completions"
            : "https://generativelanguage.googleapis.com/v1beta/models",
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setTestState({
          loading: false,
          ok: false,
          message: data.detail || "Connection test failed.",
        });
        return;
      }
      setTestState({
        loading: false,
        ok: true,
        message: `Verified! Response: "${data.reply}"`,
      });
    } catch (err) {
      setTestState({
        loading: false,
        ok: false,
        message: err.message || "Network error testing AI provider.",
      });
    }
  };

  const detectProviderModels = async (targetProvider) => {
    const isGroq = targetProvider === "groq";
    const apiKey = isGroq ? settings.groq_api_key : settings.gemini_api_key;
    const setFetched = isGroq ? setGroqFetchedModels : setGeminiFetchedModels;
    const setTestState = isGroq ? setGroqTestState : setGeminiTestState;

    if (!apiKey?.trim()) {
      setTestState({
        loading: false,
        ok: false,
        message: `Please enter a ${isGroq ? "Groq" : "Gemini"} API key first to detect models.`,
      });
      return;
    }

    try {
      const res = await fetch("/api/settings/fetch-models", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "",
        },
        body: JSON.stringify({
          ai_provider: targetProvider,
          ai_provider_api_key: apiKey.trim(),
        }),
      });
      const data = await res.json();
      if (res.ok && Array.isArray(data.models) && data.models.length > 0) {
        setFetched(data.models);
        setTestState({
          loading: false,
          ok: true,
          message: `Discovered ${data.models.length} active models on ${isGroq ? "Groq" : "Google Gemini"}!`,
        });
      } else {
        setTestState({
          loading: false,
          ok: false,
          message: data.detail || "Could not fetch models.",
        });
      }
    } catch (e) {
      setTestState({
        loading: false,
        ok: false,
        message: "Network error fetching models.",
      });
    }
  };

  const fetchAvailableModels = async () => {
    if (!settings.ai_provider_api_key?.trim()) {
      setAiTestState({
        loading: false,
        ok: false,
        message: "Please enter an API key first to discover models.",
      });
      return;
    }
    setFetchingModels(true);
    try {
      const res = await fetch("/api/settings/fetch-models", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "",
        },
        body: JSON.stringify({
          ai_provider: settings.ai_provider,
          ai_provider_api_key: settings.ai_provider_api_key.trim(),
          ai_provider_url: settings.ai_provider_url,
        }),
      });
      const data = await res.json();
      if (res.ok && Array.isArray(data.models) && data.models.length > 0) {
        setFetchedModels(data.models);
        let chosen = settings.ai_provider_model;
        if (!data.models.includes(chosen) || chosen === "gpt-4o") {
          chosen = data.models.includes("llama-3.1-8b-instant")
            ? "llama-3.1-8b-instant"
            : data.models[0];
          setSettings((prev) => ({ ...prev, ai_provider_model: chosen }));
        }
        setAiTestState({
          loading: false,
          ok: true,
          message: `Discovered ${data.models.length} active models! Selected: ${chosen}`,
        });
      } else {
        setAiTestState({
          loading: false,
          ok: false,
          message: data.detail || "Could not fetch models for this provider.",
        });
      }
    } catch (e) {
      setAiTestState({
        loading: false,
        ok: false,
        message: "Network error fetching models.",
      });
    } finally {
      setFetchingModels(false);
    }
  };

  const testAiConnection = async () => {
    if (!settings.ai_provider_api_key?.trim()) {
      setAiTestState({
        loading: false,
        ok: false,
        message: "Please enter an API key first.",
      });
      return;
    }

    const providerName =
      settings.ai_provider === "groq"
        ? "Groq Cloud"
        : settings.ai_provider === "grok"
        ? "Grok (xAI)"
        : settings.ai_provider === "gemini"
        ? "Google Gemini"
        : "AI Provider";

    const effectiveModel = resolveModelForProvider(settings.ai_provider, settings.ai_provider_model);

    setAiTestState({
      loading: true,
      ok: null,
      message: `Connecting to ${providerName} (${effectiveModel})…`,
    });

    try {
      const res = await fetch("/api/settings/test-ai", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "",
        },
        body: JSON.stringify({
          ai_provider: settings.ai_provider,
          ai_provider_api_key: settings.ai_provider_api_key.trim(),
          ai_provider_model: effectiveModel,
          ai_provider_url: settings.ai_provider_url,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setAiTestState({
          loading: false,
          ok: false,
          message: data.detail || "Connection test failed.",
        });
        return;
      }
      setAiTestState({
        loading: false,
        ok: true,
        message: `Verified! Response: "${data.reply}"`,
      });
    } catch (err) {
      setAiTestState({
        loading: false,
        ok: false,
        message: err.message || "Network error testing AI provider.",
      });
    }
  };

  const handleSave = async (e) => {
    if (e) e.preventDefault();
    setSaving(true);
    setErrorNotice("");
    setSavedNotice("");

    const activeProv = settings.ai_provider || "groq";
    const activeKey = activeProv === "groq"
      ? (settings.groq_api_key || settings.ai_provider_api_key)
      : activeProv === "gemini"
      ? (settings.gemini_api_key || settings.ai_provider_api_key)
      : settings.ai_provider_api_key;
    const activeModel = activeProv === "groq"
      ? (settings.groq_model || "openai/gpt-oss-120b")
      : activeProv === "gemini"
      ? (settings.gemini_model || "gemini-3.8-flash")
      : settings.ai_provider_model;

    const payload = {
      ...settings,
      ai_provider_api_key: activeKey,
      ai_provider_model: activeModel,
    };

    try {
      const res = await fetch("/api/settings", {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "",
        },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to save settings.");
      }
      setSettings(payload);
      setInitialSettings(payload);
      setSavedNotice("✓ Settings updated successfully. Both Groq & Gemini configurations saved!");
      await loadAuditLogs();
      setTimeout(() => setSavedNotice(""), 4000);
    } catch (err) {
      setErrorNotice(err.message || "Error saving settings.");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setSettings(initialSettings);
    setChannelInput(initialSettings.channel_id || initialSettings.channel_title || "");
    setChannelVerifyState({ loading: false, ok: null, message: "", is_admin: null });
    setAiTestState({ loading: false, ok: null, message: "" });
  };

  return (
    <div className="settings-container">
      <div className="panel-heading" style={{ marginBottom: "var(--space-6)" }}>
        <div>
          <p className="eyebrow">STUDIO CONFIGURATION</p>
          <h2>Preferences & Control Center</h2>
        </div>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          {isDirty && (
            <span className="status status-partial" style={{ fontSize: "11px" }}>
              ● Unsaved Changes
            </span>
          )}
          <button
            type="button"
            className="secondary-button"
            disabled={!isDirty || saving}
            onClick={handleReset}
            style={{ minHeight: "32px", fontSize: "12px" }}
          >
            Reset
          </button>
          <button
            type="button"
            className="primary-button"
            disabled={(!isDirty && !channelVerifyState.ok && !aiTestState.ok) || saving}
            onClick={handleSave}
            style={{ minHeight: "32px", fontSize: "12px", minWidth: "110px" }}
          >
            {saving ? "Saving…" : "Save Settings"}
          </button>
        </div>
      </div>

      {savedNotice && (
        <div className="toast toast-success" style={{ marginBottom: "var(--space-4)" }}>
          <span>{savedNotice}</span>
          <button type="button" onClick={() => setSavedNotice("")}>×</button>
        </div>
      )}

      {errorNotice && (
        <div className="toast toast-danger" style={{ marginBottom: "var(--space-4)", background: "rgba(239, 68, 68, 0.15)", color: "#ef4444", border: "1px solid rgba(239, 68, 68, 0.3)" }}>
          <span>{errorNotice}</span>
          <button type="button" onClick={() => setErrorNotice("")}>×</button>
        </div>
      )}

      {/* Section 1: Administrator & Channel Connection */}
      <section className="settings-section panel">
        <div className="settings-section-header">
          <div>
            <p className="eyebrow">INTEGRATION</p>
            <h3>Telegram Channel & Broadcast Target</h3>
          </div>
          <span className="online-dot" title="Active Connection" />
        </div>
        <div className="settings-section-body">
          <div className="settings-field-row">
            <div>
              <strong>Authorized Administrator</strong>
              <p className="muted small">Active authenticated session</p>
            </div>
            <div className="settings-field-value">
              <span className="code-badge">
                {admin ? `${admin.first_name || ""} (@${admin.username || admin.id})` : "Active Admin"}
              </span>
            </div>
          </div>

          <div className="settings-field-row" style={{ alignItems: "flex-start", paddingTop: "12px" }}>
            <div style={{ flex: 1, paddingRight: "16px" }}>
              <strong>Broadcast Channel</strong>
              <p className="muted small" style={{ margin: "2px 0 0" }}>
                Target channel for published lessons and quizzes
              </p>
            </div>
            <div className="settings-field-control-col">
              <div className="settings-input-group">
                <input
                  type="text"
                  className="settings-input"
                  placeholder="@your_channel or -100..."
                  value={channelInput}
                  onChange={(e) => setChannelInput(e.target.value)}
                />
                <button
                  type="button"
                  className="secondary-button"
                  onClick={verifyChannel}
                  disabled={channelVerifyState.loading || !channelInput.trim()}
                  style={{ minHeight: "32px", fontSize: "12px" }}
                  title="Verify channel connectivity"
                >
                  {channelVerifyState.loading ? "Checking…" : "Verify"}
                </button>
                {settings.channel_id && (
                  <button
                    type="button"
                    className="danger-button"
                    onClick={handleUnlinkChannel}
                    style={{
                      minHeight: "32px",
                      fontSize: "12px",
                      padding: "0 8px",
                      background: "rgba(239, 68, 68, 0.12)",
                      color: "#ef4444",
                      border: "1px solid rgba(239, 68, 68, 0.3)",
                      borderRadius: "var(--radius-sm, 6px)",
                      cursor: "pointer",
                    }}
                    title="Unlink channel"
                  >
                    Unlink
                  </button>
                )}
              </div>

              {channelVerifyState.message && (
                <div
                  className={`channel-status-badge ${
                    channelVerifyState.ok
                      ? channelVerifyState.is_admin
                        ? "success"
                        : "warning"
                      : "error"
                  }`}
                >
                  {channelVerifyState.ok ? (
                    channelVerifyState.is_admin ? (
                      <>✓ {channelVerifyState.message} · Bot is Admin</>
                    ) : (
                      <>⚠️ {channelVerifyState.message} · Warning: Grant bot Admin rights</>
                    )
                  ) : (
                    <>✗ {channelVerifyState.message}</>
                  )}
                </div>
              )}

              {settings.channel_title && !channelVerifyState.message && (
                <div className="channel-status-badge success">
                  ✓ Active Channel: <strong>{settings.channel_title}</strong> ({settings.channel_id})
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Section 2: Dual AI Provider Integration (Groq & Google Gemini) */}
      <section className="settings-section panel">
        <div className="settings-section-header">
          <div>
            <p className="eyebrow">INTELLIGENCE & AI ENGINE</p>
            <h3>AI Engine & Models</h3>
          </div>
          <div style={{ display: "flex", gap: "6px" }}>
            <span
              className={`status ${settings.groq_api_key ? "status-approved" : "status-failed"}`}
              style={{ fontSize: "11px" }}
            >
              {settings.groq_api_key ? "✓ Groq Ready" : "No Groq Key"}
            </span>
            <span
              className={`status ${settings.gemini_api_key ? "status-approved" : "status-failed"}`}
              style={{ fontSize: "11px" }}
            >
              {settings.gemini_api_key ? "✓ Gemini Ready" : "No Gemini Key"}
            </span>
          </div>
        </div>

        <div className="settings-section-body">
          {/* Active Provider Switcher */}
          <div className="settings-field-row" style={{ alignItems: "center", paddingBottom: "14px", borderBottom: "1px solid var(--border)" }}>
            <div>
              <strong style={{ fontSize: "14px" }}>Active Engine</strong>
            </div>
            <div className="settings-segmented-group" style={{ flexWrap: "wrap", gap: "6px" }}>
              <button
                type="button"
                className={`settings-segmented-btn ${settings.ai_provider === "groq" ? "active" : ""}`}
                onClick={() => selectAiProvider("groq")}
              >
                ⚡ Groq
              </button>
              <button
                type="button"
                className={`settings-segmented-btn ${settings.ai_provider === "gemini" ? "active" : ""}`}
                onClick={() => selectAiProvider("gemini")}
              >
                ✨ Gemini
              </button>
              <button
                type="button"
                className={`settings-segmented-btn ${settings.ai_provider === "grok" ? "active" : ""}`}
                onClick={() => selectAiProvider("grok")}
              >
                xAI Grok
              </button>
              <button
                type="button"
                className={`settings-segmented-btn ${settings.ai_provider === "custom" ? "active" : ""}`}
                onClick={() => selectAiProvider("custom")}
              >
                Custom
              </button>
            </div>
          </div>

          {/* Dual Engine Configuration Cards */}
          <div className="dual-engine-cards-grid" style={{ marginTop: "14px" }}>
            
            {/* Card 1: Groq Cloud Configuration */}
            <div
              style={{
                border: settings.ai_provider === "groq" ? "2px solid var(--accent)" : "1px solid var(--border)",
                borderRadius: "10px",
                padding: "16px",
                background: settings.ai_provider === "groq" ? "rgba(255, 255, 255, 0.03)" : "rgba(0, 0, 0, 0.2)",
                position: "relative",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                <div>
                  <h4 style={{ margin: 0, fontSize: "14px", display: "flex", alignItems: "center", gap: "6px" }}>
                    ⚡ Groq
                    {settings.ai_provider === "groq" && (
                      <span className="status status-approved" style={{ fontSize: "10px", padding: "1px 6px" }}>
                        ACTIVE
                      </span>
                    )}
                  </h4>
                </div>
                <a
                  href="https://console.groq.com/keys"
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ fontSize: "11px", color: "var(--accent)" }}
                >
                  Get Key ↗
                </a>
              </div>

              {/* Groq Key Input */}
              <div style={{ marginBottom: "10px" }}>
                <label style={{ fontSize: "11px", fontWeight: 600, display: "block", marginBottom: "4px" }}>
                  API Key
                </label>
                <div className="settings-input-group">
                  <input
                    type={showGroqKey ? "text" : "password"}
                    className="settings-input"
                    style={{ flex: 1, fontFamily: "var(--font-mono)", fontSize: "11px" }}
                    placeholder="gsk_..."
                    value={settings.groq_api_key || ""}
                    onChange={(e) => {
                      const val = e.target.value;
                      setSettings((prev) => ({
                        ...prev,
                        groq_api_key: val,
                        groq_has_key: Boolean(val.trim()),
                        ai_provider_api_key: prev.ai_provider === "groq" ? val : prev.ai_provider_api_key,
                      }));
                    }}
                  />
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => setShowGroqKey((v) => !v)}
                    style={{ minHeight: "30px", fontSize: "11px", padding: "0 8px" }}
                    title={showGroqKey ? "Hide" : "Show"}
                  >
                    {showGroqKey ? "🙈" : "👁"}
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => testProvider("groq")}
                    disabled={groqTestState.loading || !settings.groq_api_key?.trim()}
                    style={{ minHeight: "30px", fontSize: "11px", padding: "0 10px", whiteSpace: "nowrap" }}
                  >
                    {groqTestState.loading ? "…" : "Test Groq"}
                  </button>
                </div>
              </div>

              {/* Groq Model Selector */}
              <div style={{ marginBottom: "8px" }}>
                <label style={{ fontSize: "11px", fontWeight: 600, display: "block", marginBottom: "4px" }}>
                  Model
                </label>
                <div style={{ display: "flex", gap: "6px" }}>
                  {!groqCustomModelMode ? (
                    <select
                      className="settings-select"
                      style={{ flex: 1, fontSize: "12px", minHeight: "30px" }}
                      value={settings.groq_model || "openai/gpt-oss-120b"}
                      onChange={(e) => {
                        const m = e.target.value;
                        setSettings((prev) => ({
                          ...prev,
                          groq_model: m,
                          ai_provider_model: prev.ai_provider === "groq" ? m : prev.ai_provider_model,
                        }));
                      }}
                    >
                      {groqFetchedModels.length > 0 ? (
                        groqFetchedModels.map((m) => (
                          <option key={m} value={m}>{m}</option>
                        ))
                      ) : (
                        <>
                          <option value="openai/gpt-oss-120b">openai/gpt-oss-120b (Recommended)</option>
                          <option value="openai/gpt-oss-20b">openai/gpt-oss-20b</option>
                          <option value="qwen/qwen3.8-27b">qwen/qwen3.8-27b</option>
                          <option value="allam-2-7b">allam-2-7b</option>
                        </>
                      )}
                    </select>
                  ) : (
                    <input
                      type="text"
                      className="settings-input"
                      style={{ flex: 1, fontSize: "11px", fontFamily: "var(--font-mono)" }}
                      value={settings.groq_model || ""}
                      onChange={(e) => {
                        const m = e.target.value.trim();
                        setSettings((prev) => ({
                          ...prev,
                          groq_model: m,
                          ai_provider_model: prev.ai_provider === "groq" ? m : prev.ai_provider_model,
                        }));
                      }}
                      placeholder="e.g. openai/gpt-oss-120b"
                    />
                  )}
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => detectProviderModels("groq")}
                    disabled={fetchingModels || !settings.groq_api_key?.trim()}
                    style={{ minHeight: "30px", fontSize: "11px", padding: "0 8px", whiteSpace: "nowrap" }}
                    title="Detect models from Groq account"
                  >
                    🔄
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => setGroqCustomModelMode((v) => !v)}
                    style={{ minHeight: "30px", fontSize: "11px", padding: "0 8px" }}
                    title={groqCustomModelMode ? "Select from list" : "Type custom"}
                  >
                    {groqCustomModelMode ? "List" : "Edit"}
                  </button>
                </div>
              </div>

              {/* Groq Test Result */}
              {groqTestState.message && (
                <div
                  className={`channel-status-badge ${groqTestState.ok ? "success" : "error"}`}
                  style={{ marginTop: "8px", fontSize: "11px" }}
                >
                  {groqTestState.ok ? "✓ " : "✗ "}
                  {groqTestState.message}
                </div>
              )}
            </div>

            {/* Card 2: Google Gemini Configuration */}
            <div
              style={{
                border: settings.ai_provider === "gemini" ? "2px solid var(--accent)" : "1px solid var(--border)",
                borderRadius: "10px",
                padding: "16px",
                background: settings.ai_provider === "gemini" ? "rgba(255, 255, 255, 0.03)" : "rgba(0, 0, 0, 0.2)",
                position: "relative",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                <div>
                  <h4 style={{ margin: 0, fontSize: "14px", display: "flex", alignItems: "center", gap: "6px" }}>
                    ✨ Gemini
                    {settings.ai_provider === "gemini" && (
                      <span className="status status-approved" style={{ fontSize: "10px", padding: "1px 6px" }}>
                        ACTIVE
                      </span>
                    )}
                  </h4>
                </div>
                <a
                  href="https://aistudio.google.com/app/apikey"
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ fontSize: "11px", color: "var(--accent)" }}
                >
                  Get Key ↗
                </a>
              </div>

              {/* Gemini Key Input */}
              <div style={{ marginBottom: "10px" }}>
                <label style={{ fontSize: "11px", fontWeight: 600, display: "block", marginBottom: "4px" }}>
                  API Key
                </label>
                <div className="settings-input-group">
                  <input
                    type={showGeminiKey ? "text" : "password"}
                    className="settings-input"
                    style={{ flex: 1, fontFamily: "var(--font-mono)", fontSize: "11px" }}
                    placeholder="AIzaSy... or AQ..."
                    value={settings.gemini_api_key || ""}
                    onChange={(e) => {
                      const val = e.target.value;
                      setSettings((prev) => ({
                        ...prev,
                        gemini_api_key: val,
                        gemini_has_key: Boolean(val.trim()),
                        ai_provider_api_key: prev.ai_provider === "gemini" ? val : prev.ai_provider_api_key,
                      }));
                    }}
                  />
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => setShowGeminiKey((v) => !v)}
                    style={{ minHeight: "30px", fontSize: "11px", padding: "0 8px" }}
                    title={showGeminiKey ? "Hide" : "Show"}
                  >
                    {showGeminiKey ? "🙈" : "👁"}
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => testProvider("gemini")}
                    disabled={geminiTestState.loading || !settings.gemini_api_key?.trim()}
                    style={{ minHeight: "30px", fontSize: "11px", padding: "0 10px", whiteSpace: "nowrap" }}
                  >
                    {geminiTestState.loading ? "…" : "Test Gemini"}
                  </button>
                </div>
              </div>

              {/* Gemini Model Selector */}
              <div style={{ marginBottom: "8px" }}>
                <label style={{ fontSize: "11px", fontWeight: 600, display: "block", marginBottom: "4px" }}>
                  Model
                </label>
                <div style={{ display: "flex", gap: "6px" }}>
                  {!geminiCustomModelMode ? (
                    <select
                      className="settings-select"
                      style={{ flex: 1, fontSize: "12px", minHeight: "30px" }}
                      value={settings.gemini_model || "gemini-3-flash-preview"}
                      onChange={(e) => {
                        const m = e.target.value;
                        setSettings((prev) => ({
                          ...prev,
                          gemini_model: m,
                          ai_provider_model: prev.ai_provider === "gemini" ? m : prev.ai_provider_model,
                        }));
                      }}
                    >
                      {geminiFetchedModels.length > 0 ? (
                        geminiFetchedModels.map((m) => (
                          <option key={m} value={m}>{m}</option>
                        ))
                      ) : (
                        <>
                          <option value="gemini-3-flash-preview">gemini-3-flash-preview (Recommended)</option>
                          <option value="gemini-flash-lite-latest">gemini-flash-lite-latest</option>
                          <option value="gemini-3.8-flash">gemini-3.8-flash</option>
                          <option value="gemini-3.8-pro">gemini-3.8-pro</option>
                          <option value="gemini-pro-latest">gemini-pro-latest</option>
                        </>
                      )}
                    </select>
                  ) : (
                    <input
                      type="text"
                      className="settings-input"
                      style={{ flex: 1, fontSize: "11px", fontFamily: "var(--font-mono)" }}
                      value={settings.gemini_model || ""}
                      onChange={(e) => {
                        const m = e.target.value.trim();
                        setSettings((prev) => ({
                          ...prev,
                          gemini_model: m,
                          ai_provider_model: prev.ai_provider === "gemini" ? m : prev.ai_provider_model,
                        }));
                      }}
                      placeholder="e.g. gemini-3.8-flash"
                    />
                  )}
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => detectProviderModels("gemini")}
                    disabled={fetchingModels || !settings.gemini_api_key?.trim()}
                    style={{ minHeight: "30px", fontSize: "11px", padding: "0 8px", whiteSpace: "nowrap" }}
                    title="Detect models from Gemini AI Studio"
                  >
                    🔄
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => setGeminiCustomModelMode((v) => !v)}
                    style={{ minHeight: "30px", fontSize: "11px", padding: "0 8px" }}
                    title={geminiCustomModelMode ? "Select from list" : "Type custom"}
                  >
                    {geminiCustomModelMode ? "List" : "Edit"}
                  </button>
                </div>
              </div>

              {/* Gemini Test Result */}
              {geminiTestState.message && (
                <div
                  className={`channel-status-badge ${geminiTestState.ok ? "success" : "error"}`}
                  style={{ marginTop: "8px", fontSize: "11px" }}
                >
                  {geminiTestState.ok ? "✓ " : "✗ "}
                  {geminiTestState.message}
                </div>
              )}
            </div>

          </div>

          {/* Advanced Endpoint Option if Grok or Custom selected */}
          {(settings.ai_provider === "grok" || settings.ai_provider === "custom") && (
            <div style={{ marginTop: "16px", padding: "14px", border: "1px dashed var(--border)", borderRadius: "8px" }}>
              <div className="settings-field-row" style={{ alignItems: "center" }}>
                <div>
                  <strong>{settings.ai_provider === "grok" ? "xAI Grok API Key" : "Custom API Key"}</strong>
                  <p className="muted small" style={{ margin: "2px 0 0" }}>Bearer token for this engine</p>
                </div>
                <div className="settings-input-group settings-field-control-col">
                  <input
                    type="password"
                    className="settings-input"
                    value={settings.ai_provider === "grok" ? (settings.grok_api_key || "") : (settings.ai_provider_api_key || "")}
                    onChange={(e) => {
                      const val = e.target.value;
                      if (settings.ai_provider === "grok") {
                        setSettings((s) => ({ ...s, grok_api_key: val, ai_provider_api_key: val }));
                      } else {
                        setSettings((s) => ({ ...s, ai_provider_api_key: val }));
                      }
                    }}
                    placeholder="Key..."
                  />
                </div>
              </div>
              <div className="settings-field-row" style={{ marginTop: "10px" }}>
                <div>
                  <strong>Endpoint URL</strong>
                  <p className="muted small" style={{ margin: "2px 0 0" }}>Custom destination URL</p>
                </div>
                <input
                  type="text"
                  className="settings-input"
                  style={{ width: "320px", fontSize: "11px", fontFamily: "var(--font-mono)" }}
                  value={settings.ai_provider_url || ""}
                  onChange={(e) => setSettings((s) => ({ ...s, ai_provider_url: e.target.value }))}
                />
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Section 3: Publishing & Delivery Format */}
      <section className="settings-section panel">
        <div className="settings-section-header">
          <div>
            <p className="eyebrow">DISTRIBUTION</p>
            <h3>Publishing & Layout Formatting</h3>
          </div>
        </div>
        <div className="settings-section-body">
          <div className="settings-field-row">
            <div>
              <strong>Default Delivery Mode</strong>
              <p className="muted small">How lessons are formatted when broadcast to your channel</p>
            </div>
            <div className="settings-segmented-group">
              <button
                type="button"
                className={`settings-segmented-btn ${settings.delivery_mode === "card" ? "active" : ""}`}
                onClick={() => setSettings((s) => ({ ...s, delivery_mode: "card" }))}
              >
                📄 Card + PDF Link
              </button>
              <button
                type="button"
                className={`settings-segmented-btn ${settings.delivery_mode === "full_text" ? "active" : ""}`}
                onClick={() => setSettings((s) => ({ ...s, delivery_mode: "full_text" }))}
              >
                📝 Full Text
              </button>
              <button
                type="button"
                className={`settings-segmented-btn ${settings.delivery_mode === "both" ? "active" : ""}`}
                onClick={() => setSettings((s) => ({ ...s, delivery_mode: "both" }))}
              >
                📑 Hybrid (Both)
              </button>
            </div>
          </div>

          <div className="settings-field-row">
            <div>
              <strong>Header Presentation Style</strong>
              <p className="muted small">Visual banner badge on reader preview & exported PDF</p>
            </div>
            <div>
              <select
                className="settings-select"
                value={settings.post_header_style}
                onChange={(e) => setSettings((s) => ({ ...s, post_header_style: e.target.value }))}
              >
                <option value="academic">🛡️ Academic Courseware (Verified Standard)</option>
                <option value="standard">📘 Standard Courseware</option>
                <option value="minimal">📄 Minimalist (Title & Source)</option>
              </select>
            </div>
          </div>

          <div className="settings-field-row">
            <div>
              <strong>Institutional Branding Signature</strong>
              <p className="muted small">Author organization printed on PDF header & channel footer</p>
            </div>
            <div>
              <input
                type="text"
                className="settings-input"
                style={{ width: "240px" }}
                value={settings.branding_signature}
                onChange={(e) => setSettings((s) => ({ ...s, branding_signature: e.target.value }))}
                placeholder="e.g. CyberLearn Academic Team"
              />
            </div>
          </div>
        </div>
      </section>

      {/* Section 4: Editorial Workflow & Safety Policies */}
      <section className="settings-section panel">
        <div className="settings-section-header">
          <div>
            <p className="eyebrow">EDITORIAL WORKFLOW</p>
            <h3>Review Policies & Quiz Controls</h3>
          </div>
        </div>
        <div className="settings-section-body">
          <div className="settings-field-row">
            <div>
              <strong>Mandatory Approval Gate</strong>
              <p className="muted small">Require human "✓ Approve" review before any lesson or quiz can be published</p>
            </div>
            <div>
              <label className="switch">
                <input
                  type="checkbox"
                  checked={settings.require_approval}
                  onChange={(e) => setSettings((s) => ({ ...s, require_approval: e.target.checked }))}
                />
                <span className="slider" />
              </label>
            </div>
          </div>

          <div className="settings-field-row">
            <div>
              <strong>Anonymous Quiz Polls</strong>
              <p className="muted small">Hide student voter identities in Telegram channel quiz polls</p>
            </div>
            <div>
              <label className="switch">
                <input
                  type="checkbox"
                  checked={settings.quiz_anonymous}
                  onChange={(e) => setSettings((s) => ({ ...s, quiz_anonymous: e.target.checked }))}
                />
                <span className="slider" />
              </label>
            </div>
          </div>

          <div className="settings-field-row">
            <div>
              <strong>Default Quiz Time Limit</strong>
              <p className="muted small">Default duration suggested when authoring new timed quizzes</p>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <input
                type="number"
                min="1"
                max="180"
                className="settings-input"
                style={{ width: "70px", textAlign: "center" }}
                value={settings.quiz_default_duration}
                onChange={(e) => setSettings((s) => ({ ...s, quiz_default_duration: Number(e.target.value) || 10 }))}
              />
              <span className="muted small">minutes</span>
            </div>
          </div>

          <div className="settings-field-row">
            <div>
              <strong>Passing Score Target</strong>
              <p className="muted small">Benchmark accuracy required to achieve courseware certification</p>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <input
                type="number"
                min="10"
                max="100"
                step="5"
                className="settings-input"
                style={{ width: "70px", textAlign: "center" }}
                value={settings.quiz_pass_percentage}
                onChange={(e) => setSettings((s) => ({ ...s, quiz_pass_percentage: Number(e.target.value) || 70 }))}
              />
              <span className="muted small">%</span>
            </div>
          </div>

          <div className="settings-field-row">
            <div>
              <strong>Auto-Save Drafts in Studio</strong>
              <p className="muted small">Automatically save lesson and quiz drafts as you type</p>
            </div>
            <div>
              <label className="switch">
                <input
                  type="checkbox"
                  checked={settings.autosave_enabled}
                  onChange={(e) => setSettings((s) => ({ ...s, autosave_enabled: e.target.checked }))}
                />
                <span className="slider" />
              </label>
            </div>
          </div>

          {settings.autosave_enabled && (
            <div className="settings-field-row">
              <div>
                <strong>Auto-Save Debounce Interval</strong>
                <p className="muted small">Delay after typing stops before saving draft</p>
              </div>
              <div>
                <select
                  className="settings-select"
                  value={settings.autosave_interval}
                  onChange={(e) => setSettings((s) => ({ ...s, autosave_interval: Number(e.target.value) }))}
                >
                  <option value={1}>1 second (Instant)</option>
                  <option value={2}>2 seconds (Standard)</option>
                  <option value={3}>3 seconds (Conservative)</option>
                  <option value={5}>5 seconds</option>
                </select>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Section 5: Appearance & Theme */}
      <section className="settings-section panel">
        <div className="settings-section-header">
          <div>
            <p className="eyebrow">INTERFACE</p>
            <h3>Theme & Visual Display</h3>
          </div>
        </div>
        <div className="settings-section-body">
          <div className="settings-field-row">
            <div>
              <strong>Current Theme</strong>
              <p className="muted small">Active appearance: {resolvedTheme} mode</p>
            </div>
            <div className="theme-selector-group">
              <button
                type="button"
                className={`secondary-button ${theme === "light" ? "selected" : ""}`}
                onClick={() => setTheme("light")}
              >
                ☀️ Light Mode
              </button>
              <button
                type="button"
                className={`secondary-button ${theme === "dark" ? "selected" : ""}`}
                onClick={() => setTheme("dark")}
              >
                🌙 Dark Mode
              </button>
              <button
                type="button"
                className={`secondary-button ${theme === "system" ? "selected" : ""}`}
                onClick={() => setTheme("system")}
              >
                🖥️ Follow Device
              </button>
            </div>
          </div>

          <div className="settings-field-row">
            <div>
              <strong>Color Palette</strong>
              <p className="muted small">CyberLearn Studio design tokens</p>
            </div>
            <div className="palette-preview-row">
              <span className="palette-swatch" style={{ background: "var(--bg)", border: "1px solid var(--border)" }} title="Background" />
              <span className="palette-swatch" style={{ background: "var(--surface)", border: "1px solid var(--border)" }} title="Surface" />
              <span className="palette-swatch" style={{ background: "var(--accent)" }} title="Accent" />
              <span className="palette-swatch" style={{ background: "var(--success)" }} title="Success" />
              <span className="palette-swatch" style={{ background: "var(--warning)" }} title="Warning" />
            </div>
          </div>
        </div>
      </section>

      {/* Sticky Bottom Actions Bar */}
      <div className="settings-actions-footer">
        {isDirty && (
          <span className="status status-partial" style={{ marginRight: "auto" }}>
            ● You have unsaved changes in settings.
          </span>
        )}
        <button
          type="button"
          className="secondary-button"
          disabled={!isDirty || saving}
          onClick={handleReset}
        >
          Cancel
        </button>
        <button
          type="button"
          className="primary-button"
          disabled={!isDirty || saving}
          onClick={handleSave}
          style={{ minWidth: "140px" }}
        >
          {saving ? "Saving Changes…" : "Save Preferences"}
        </button>
      </div>

      {/* Section 6: System Audit Log */}
      <section className="settings-section panel" style={{ marginTop: "var(--space-6)" }}>
        <div className="settings-section-header">
          <div>
            <p className="eyebrow">GOVERNANCE & AUDIT</p>
            <h3>Administrative Trail</h3>
          </div>
          <button
            type="button"
            className="secondary-button"
            style={{ minHeight: "30px", fontSize: "12px" }}
            onClick={loadAuditLogs}
            disabled={loadingAudit}
          >
            {loadingAudit ? "Loading…" : "Refresh Audit Log"}
          </button>
        </div>
        <div className="settings-section-body">
          {auditLogs.length > 0 ? (
            <div className="audit-log-table-wrapper">
              <table className="publishing-table">
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Action</th>
                    <th>Target Type</th>
                    <th>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {auditLogs.map((log) => (
                    <tr key={log.id}>
                      <td className="muted small">
                        {new Date(log.created_at).toLocaleString()}
                      </td>
                      <td>
                        <strong>{log.action}</strong>
                      </td>
                      <td>
                        <span className="code-badge">{log.target_type} #{log.target_id || "—"}</span>
                      </td>
                      <td className="muted small">
                        {log.after_value ? JSON.stringify(log.after_value).slice(0, 90) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="empty-note">
              {loadingAudit ? "Fetching administrative audit trail…" : "No audit events logged yet."}
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
