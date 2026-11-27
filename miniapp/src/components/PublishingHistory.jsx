import { useCallback, useEffect, useState } from "react";

export function PublishingHistory({ busy }) {
  const [activity, setActivity] = useState([]);
  const [loading, setLoading] = useState(false);

  const loadHistory = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetch("/api/dashboard", {
        headers: {
          "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "",
        },
      });
      if (data.ok) {
        const dashboard = await data.json();
        setActivity(dashboard.recent_activity || []);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">PUBLISHING HISTORY</p>
          <h2>Delivery Records</h2>
        </div>
        <button
          className="text-button"
          disabled={busy}
          onClick={loadHistory}
        >
          Refresh
        </button>
      </div>

      {loading ? (
        <div className="empty-state" style={{ justifyContent: "center" }}>
          <p className="muted">Loading publishing history…</p>
        </div>
      ) : activity.length > 0 ? (
        <div className="activity-list">
          {activity.map((item) => (
            <article key={item.job_id} className="activity-item">
              <div className="activity-main">
                <strong>{item.lesson_title}</strong>
                <span>{item.course_title}</span>
              </div>
              <div className="activity-details">
                <code>{item.channel_id}</code>
                <span
                  className={`status status-${item.status}`}
                >
                  {item.status}
                </span>
                {item.telegram_message_ids?.length > 0 && (
                  <small>
                    Messages: {item.telegram_message_ids.join(", ")}
                  </small>
                )}
                {item.error && (
                  <small className="history-error">{item.error}</small>
                )}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <div className="empty-art">📬</div>
          <h3>No publishing history</h3>
          <p className="muted">Published lessons will appear here.</p>
        </div>
      )}
    </section>
  );
}
