export function Dashboard({ dashboard, busy, onRefresh }) {
  const readyCount = dashboard?.ready_count ?? 0;
  const draftCount = dashboard?.draft_count ?? 0;
  const failedCount = dashboard?.failed_publish_count ?? 0;
  const publishedCount = dashboard?.published_count ?? 0;
  const courseCount = dashboard?.course_count ?? 0;
  const lessonCount = dashboard?.lesson_count ?? 0;

  return (
    <section className="dashboard-section" aria-label="Studio dashboard">
      {/* Compact Actionable Status Strip */}
      <div className="dashboard-overview">
        <div className="dashboard-summary-text">
          <h2>Workspace status</h2>
          <p className="muted">
            {courseCount} active {courseCount === 1 ? "course" : "courses"} · {lessonCount} total {lessonCount === 1 ? "lesson" : "lessons"}
          </p>
        </div>

        <div className="dashboard-action-items">
          {failedCount > 0 && (
            <div className="action-pill action-pill-danger" title="Deliveries that encountered errors and need review">
              <span className="action-pill-dot" />
              <strong>{failedCount}</strong> failed delivery {failedCount === 1 ? "needs" : "need"} retry
            </div>
          )}

          {readyCount > 0 && (
            <div className="action-pill action-pill-success" title="Approved lessons ready to be sent to Telegram">
              <span className="action-pill-dot" />
              <strong>{readyCount}</strong> ready to publish
            </div>
          )}

          <div className="action-pill" title="Lessons currently in draft">
            <span className="action-pill-dot neutral" />
            <span>{draftCount} in draft</span>
          </div>

          <div className="action-pill" title="Lessons successfully published to Telegram">
            <span className="action-pill-dot published" />
            <span>{publishedCount} published</span>
          </div>
        </div>
      </div>

      {/* Activity Panel */}
      <section className="activity-panel panel">
        <div className="activity-heading">
          <div>
            <p className="eyebrow">TELEGRAM CHANNEL</p>
            <h3>Recent publishing activity</h3>
          </div>
          <button
            type="button"
            className="secondary-button"
            disabled={busy}
            onClick={onRefresh}
            style={{ minHeight: "32px", padding: "0 var(--space-3)", fontSize: "12px" }}
          >
            {busy ? "Refreshing…" : "Refresh"}
          </button>
        </div>

        {dashboard?.recent_activity?.length ? (
          <div className="activity-list">
            {dashboard.recent_activity.map((activity) => (
              <article className="activity-item" key={activity.job_id}>
                <div className="activity-main">
                  <strong>{activity.lesson_title}</strong>
                  <span>{activity.course_title} · {new Date(activity.updated_at).toLocaleString()}</span>
                </div>
                <div className="activity-details">
                  <span className={`status status-${activity.status}`}>{activity.status}</span>
                  {activity.telegram_message_ids?.length > 0 && (
                    <small className="muted">Msg #{activity.telegram_message_ids.join(", #")}</small>
                  )}
                  {activity.error && <small className="history-error">{activity.error}</small>}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-state" style={{ padding: "var(--space-6) var(--space-4)" }}>
            <p className="muted" style={{ margin: 0, fontSize: "13px" }}>
              {dashboard
                ? "No publishing history recorded yet. Approved lessons published to your channel will be tracked here."
                : "Loading publishing records…"}
            </p>
          </div>
        )}
      </section>
    </section>
  );
}
