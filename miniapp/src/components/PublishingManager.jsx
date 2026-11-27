import { useCallback, useEffect, useState } from "react";

export function PublishingManager({
  busy,
  onOpenLesson,
  onOpenCalendar,
}) {
  const [filter, setFilter] = useState("all");
  const [courses, setCourses] = useState([]);
  const [allLessons, setAllLessons] = useState([]);
  const [scheduledItems, setScheduledItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [coursesRes, scheduledRes] = await Promise.all([
        fetch("/api/courses?include_archived=false", {
          headers: { "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "" },
        }),
        fetch("/api/scheduled", {
          headers: { "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "" },
        }),
      ]);

      let coursesData = [];
      if (coursesRes.ok) {
        coursesData = await coursesRes.json();
        setCourses(coursesData);
      }

      let scheduledData = [];
      if (scheduledRes.ok) {
        scheduledData = await scheduledRes.json();
        setScheduledItems(scheduledData);
      }

      // Load all lessons across courses
      const lessonsList = [];
      for (const course of coursesData) {
        const lRes = await fetch(`/api/courses/${course.id}/lessons`, {
          headers: { "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "" },
        });
        if (lRes.ok) {
          const courseLessons = await lRes.json();
          for (const l of courseLessons) {
            const scheduled = scheduledData.find((s) => s.lesson_id === l.id && s.status === "pending");
            lessonsList.push({
              ...l,
              course_title: course.title,
              is_scheduled: Boolean(scheduled),
              scheduled_data: scheduled,
            });
          }
        }
      }
      setAllLessons(lessonsList);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handlePublishNow = async (lessonId) => {
    try {
      const res = await fetch(`/api/lessons/${lessonId}/publish`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "",
        },
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Publishing failed.");
      }
      setNotice("Lesson successfully published to Telegram channel.");
      await loadData();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleApproveAndPublish = async (lessonId) => {
    try {
      const appRes = await fetch(`/api/lessons/${lessonId}/approve`, {
        method: "POST",
        headers: { "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "" },
      });
      if (!appRes.ok) throw new Error("Approval failed.");

      const pubRes = await fetch(`/api/lessons/${lessonId}/publish`, {
        method: "POST",
        headers: { "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "" },
      });
      if (!pubRes.ok) throw new Error("Publishing failed after approval.");

      setNotice("Version approved and published to Telegram.");
      await loadData();
    } catch (err) {
      setError(err.message);
    }
  };

  const filteredLessons = allLessons.filter((l) => {
    if (filter === "ready") return l.status === "approved";
    if (filter === "queued") return l.is_scheduled;
    if (filter === "published") return l.status === "published";
    if (filter === "failed") return l.status === "failed" || l.status === "partial";
    if (filter === "draft") return l.status === "draft";
    return true;
  });

  const counts = {
    all: allLessons.length,
    ready: allLessons.filter((l) => l.status === "approved").length,
    queued: allLessons.filter((l) => l.is_scheduled).length,
    published: allLessons.filter((l) => l.status === "published").length,
    failed: allLessons.filter((l) => l.status === "failed" || l.status === "partial").length,
    draft: allLessons.filter((l) => l.status === "draft").length,
  };

  return (
    <section className="panel publishing-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">DISTRIBUTION & AUDIENCE DELIVERY</p>
          <h2>Publishing Operations</h2>
        </div>
        <div style={{ display: "flex", gap: "var(--space-2)" }}>
          {onOpenCalendar && (
            <button type="button" className="secondary-button" onClick={onOpenCalendar}>
              📅 Open Publishing Calendar
            </button>
          )}
          <button type="button" className="ghost-button" disabled={busy || loading} onClick={loadData}>
            {loading ? "Loading…" : "Refresh"}
          </button>
        </div>
      </div>

      {notice && (
        <div className="toast toast-success" style={{ margin: "var(--space-4) var(--space-6) 0" }}>
          {notice}
          <button type="button" onClick={() => setNotice("")}>×</button>
        </div>
      )}

      {error && (
        <div className="toast toast-error" style={{ margin: "var(--space-4) var(--space-6) 0" }}>
          {error}
          <button type="button" onClick={() => setError("")}>×</button>
        </div>
      )}

      {/* Workflow Tabs */}
      <div className="publishing-filter-tabs">
        <button
          type="button"
          className={`filter-tab ${filter === "all" ? "active" : ""}`}
          onClick={() => setFilter("all")}
        >
          All ({counts.all})
        </button>
        <button
          type="button"
          className={`filter-tab ${filter === "ready" ? "active" : ""}`}
          onClick={() => setFilter("ready")}
        >
          Ready to Publish ({counts.ready})
        </button>
        <button
          type="button"
          className={`filter-tab ${filter === "queued" ? "active" : ""}`}
          onClick={() => setFilter("queued")}
        >
          Queued ({counts.queued})
        </button>
        <button
          type="button"
          className={`filter-tab ${filter === "published" ? "active" : ""}`}
          onClick={() => setFilter("published")}
        >
          Published ({counts.published})
        </button>
        <button
          type="button"
          className={`filter-tab ${filter === "draft" ? "active" : ""}`}
          onClick={() => setFilter("draft")}
        >
          Drafts ({counts.draft})
        </button>
        <button
          type="button"
          className={`filter-tab filter-tab-danger ${filter === "failed" ? "active" : ""}`}
          onClick={() => setFilter("failed")}
        >
          Failed ({counts.failed})
        </button>
      </div>

      {/* Publishing Table / List */}
      <div className="publishing-table-container">
        {filteredLessons.length > 0 ? (
          <table className="publishing-table">
            <thead>
              <tr>
                <th>Lesson & Course</th>
                <th>Status</th>
                <th>Last Updated</th>
                <th>Schedule / Delivery</th>
                <th style={{ textAlign: "right" }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredLessons.map((item) => {
                const isApproved = item.status === "approved";
                const isPublished = item.status === "published";
                const isFailed = item.status === "failed" || item.status === "partial";
                const isDraft = item.status === "draft";

                return (
                  <tr key={item.id} className="publishing-row">
                    <td>
                      <div className="publishing-title-cell">
                        <strong>{item.title}</strong>
                        <span className="muted small">{item.course_title}</span>
                      </div>
                    </td>
                    <td>
                      <span className={`status status-${item.status}`}>
                        {item.status}
                      </span>
                    </td>
                    <td className="muted small">
                      {new Date(item.updated_at).toLocaleDateString()}
                    </td>
                    <td>
                      {item.is_scheduled ? (
                        <span className="scheduled-indicator">
                          🕒 Scheduled for {new Date(item.scheduled_data.scheduled_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                        </span>
                      ) : isPublished ? (
                        <span className="delivered-indicator">
                          ✓ Telegram Channel
                        </span>
                      ) : isFailed ? (
                        <span className="history-error">
                          Delivery error
                        </span>
                      ) : (
                        <span className="muted small">Not scheduled</span>
                      )}
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <div className="publishing-row-actions">
                        {isApproved && (
                          <button
                            type="button"
                            className="publish-button"
                            onClick={() => handlePublishNow(item.id)}
                            disabled={busy}
                          >
                            Publish ↗
                          </button>
                        )}
                        {isFailed && (
                          <button
                            type="button"
                            className="publish-button"
                            onClick={() => handlePublishNow(item.id)}
                            disabled={busy}
                          >
                            ↻ Retry
                          </button>
                        )}
                        {isDraft && (
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() => onOpenLesson && onOpenLesson(item.id, item.course_id)}
                          >
                            Open Editor
                          </button>
                        )}
                        {onOpenLesson && !isDraft && (
                          <button
                            type="button"
                            className="text-button"
                            onClick={() => onOpenLesson(item.id, item.course_id)}
                          >
                            Edit
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <div className="empty-state" style={{ padding: "var(--space-10) var(--space-4)" }}>
            <div className="empty-art">✦</div>
            <h3>No lessons match this filter</h3>
            <p className="muted">
              {filter === "ready"
                ? "No approved lessons waiting to publish. Approve drafts in the lesson editor."
                : filter === "queued"
                  ? "No scheduled publications found. Schedule lessons using the Publishing Calendar."
                  : filter === "failed"
                    ? "No failed delivery attempts. All publications are healthy."
                    : "No lessons found."}
            </p>
          </div>
        )}
      </div>
    </section>
  );
}

