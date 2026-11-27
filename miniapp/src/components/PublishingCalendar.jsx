import { useCallback, useEffect, useState } from "react";

export function PublishingCalendar({ busy, onNavigateLesson, confirmAction }) {
  const [scheduledItems, setScheduledItems] = useState([]);
  const [courses, setCourses] = useState([]);
  const [approvedLessons, setApprovedLessons] = useState([]);
  const [currentDate, setCurrentDate] = useState(() => new Date());
  const [selectedDate, setSelectedDate] = useState(null);
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [scheduleForm, setScheduleForm] = useState({
    lesson_id: "",
    scheduled_at: "",
    channel_id: "",
  });
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const loadScheduled = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/scheduled", {
        headers: {
          "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "",
        },
      });
      if (res.ok) {
        const data = await res.json();
        setScheduledItems(data);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadApprovedLessons = useCallback(async () => {
    try {
      const res = await fetch("/api/courses?include_archived=false", {
        headers: {
          "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "",
        },
      });
      if (res.ok) {
        const courseList = await res.json();
        setCourses(courseList);
        const allLessons = [];
        for (const course of courseList) {
          const lRes = await fetch(`/api/courses/${course.id}/lessons`, {
            headers: {
              "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "",
            },
          });
          if (lRes.ok) {
            const lessons = await lRes.json();
            for (const l of lessons) {
              if (l.status === "approved" || l.status === "draft") {
                allLessons.push({ ...l, course_title: course.title });
              }
            }
          }
        }
        setApprovedLessons(allLessons);
      }
    } catch (e) {
      // ignore
    }
  }, []);

  useEffect(() => {
    loadScheduled();
    loadApprovedLessons();
  }, [loadScheduled, loadApprovedLessons]);

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  const prevMonth = () => setCurrentDate(new Date(year, month - 1, 1));
  const nextMonth = () => setCurrentDate(new Date(year, month + 1, 1));
  const goToToday = () => {
    const today = new Date();
    setCurrentDate(today);
    setSelectedDate(today.toISOString().split("T")[0]);
  };

  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const firstDayIndex = (new Date(year, month, 1).getDay() + 6) % 7; // Monday = 0

  const monthName = currentDate.toLocaleString("default", { month: "long" });

  const getItemsForDate = (dateStr) => {
    return scheduledItems.filter((item) => {
      if (!item.scheduled_at) return false;
      const itemDate = new Date(item.scheduled_at).toISOString().split("T")[0];
      return itemDate === dateStr;
    });
  };

  const handleScheduleSubmit = async (e) => {
    e.preventDefault();
    if (!scheduleForm.lesson_id || !scheduleForm.scheduled_at) return;
    try {
      const res = await fetch("/api/scheduled", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "",
        },
        body: JSON.stringify({
          lesson_id: Number(scheduleForm.lesson_id),
          scheduled_at: new Date(scheduleForm.scheduled_at).toISOString(),
          channel_id: scheduleForm.channel_id || null,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Failed to schedule publication.");
      }
      setNotice("Lesson scheduled successfully.");
      setShowScheduleModal(false);
      setScheduleForm({ lesson_id: "", scheduled_at: "", channel_id: "" });
      await loadScheduled();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleCancelScheduled = async (publicationId) => {
    if (confirmAction) {
      const ok = await confirmAction({
        title: "Cancel Publication?",
        message: "Cancel this scheduled publication?",
        confirmText: "Cancel Publication",
        danger: true,
      });
      if (!ok) return;
    }
    try {
      const res = await fetch(`/api/scheduled/${publicationId}`, {
        method: "DELETE",
        headers: {
          "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "",
        },
      });
      if (!res.ok) throw new Error("Failed to cancel publication.");
      setNotice("Scheduled publication cancelled.");
      await loadScheduled();
    } catch (err) {
      setError(err.message);
    }
  };

  const selectedDateItems = selectedDate ? getItemsForDate(selectedDate) : [];
  const todayStr = new Date().toISOString().split("T")[0];

  return (
    <section className="panel calendar-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">PUBLISHING SCHEDULE</p>
          <h2>Editorial Calendar</h2>
        </div>
        <div className="calendar-controls">
          <button type="button" className="secondary-button" onClick={prevMonth} aria-label="Previous month">
            ‹ Prev
          </button>
          <button type="button" className="ghost-button" onClick={goToToday}>
            Today
          </button>
          <button type="button" className="secondary-button" onClick={nextMonth} aria-label="Next month">
            Next ›
          </button>
          <button
            type="button"
            className="publish-button"
            onClick={() => {
              const defaultDate = selectedDate || todayStr;
              setScheduleForm((prev) => ({
                ...prev,
                scheduled_at: `${defaultDate}T12:00`,
              }));
              setShowScheduleModal(true);
            }}
          >
            ＋ Schedule Lesson
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

      <div className="calendar-month-header">
        <h3>{monthName} {year}</h3>
        <span className="muted small">
          {scheduledItems.filter((i) => i.status === "pending" || i.status === "queued").length} queued upcoming
        </span>
      </div>

      <div className="calendar-grid-wrapper">
        <div className="calendar-weekdays">
          <span>Mon</span>
          <span>Tue</span>
          <span>Wed</span>
          <span>Thu</span>
          <span>Fri</span>
          <span>Sat</span>
          <span>Sun</span>
        </div>

        <div className="calendar-grid">
          {Array.from({ length: firstDayIndex }).map((_, i) => (
            <div key={`empty-${i}`} className="calendar-cell empty" />
          ))}

          {Array.from({ length: daysInMonth }).map((_, i) => {
            const dayNum = i + 1;
            const dayStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(dayNum).padStart(2, "0")}`;
            const items = getItemsForDate(dayStr);
            const isToday = dayStr === todayStr;
            const isSelected = dayStr === selectedDate;

            return (
              <div
                key={dayStr}
                className={`calendar-cell ${isToday ? "today" : ""} ${isSelected ? "selected" : ""} ${items.length ? "has-events" : ""}`}
                onClick={() => setSelectedDate(dayStr)}
              >
                <div className="calendar-date-number">
                  <span>{dayNum}</span>
                  {items.length > 0 && <span className="calendar-badge-count">{items.length}</span>}
                </div>

                <div className="calendar-events-preview">
                  {items.slice(0, 2).map((item) => (
                    <div
                      key={item.id}
                      className={`calendar-event-chip status-${item.status}`}
                      title={`${item.lesson_title} (${item.status})`}
                    >
                      <span className="calendar-event-time">
                        {new Date(item.scheduled_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </span>
                      <span className="calendar-event-title">{item.lesson_title}</span>
                    </div>
                  ))}
                  {items.length > 2 && (
                    <span className="calendar-more-events">+{items.length - 2} more</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Selected Day Agenda */}
      <div className="calendar-agenda">
        <div className="calendar-agenda-header">
          <div>
            <p className="eyebrow">AGENDA</p>
            <h4>
              {selectedDate
                ? new Date(selectedDate + "T00:00:00").toLocaleDateString(undefined, {
                    weekday: "long",
                    month: "long",
                    day: "numeric",
                    year: "numeric",
                  })
                : "Select a date to view scheduled posts"}
            </h4>
          </div>
          {selectedDate && (
            <button
              type="button"
              className="secondary-button"
              onClick={() => {
                setScheduleForm({
                  lesson_id: "",
                  scheduled_at: `${selectedDate}T12:00`,
                  channel_id: "",
                });
                setShowScheduleModal(true);
              }}
            >
              ＋ Add post for this day
            </button>
          )}
        </div>

        {selectedDateItems.length > 0 ? (
          <div className="agenda-items-list">
            {selectedDateItems.map((item) => (
              <div key={item.id} className="agenda-item">
                <div className="agenda-time">
                  <strong>{new Date(item.scheduled_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</strong>
                  <span className={`status status-${item.status}`}>{item.status}</span>
                </div>
                <div className="agenda-content">
                  <strong>{item.lesson_title}</strong>
                  <span className="muted small">{item.course_title} · Target: {item.channel_id || "Default Telegram Channel"}</span>
                  {item.error && <p className="history-error">{item.error}</p>}
                </div>
                <div className="agenda-actions">
                  {onNavigateLesson && (
                    <button
                      type="button"
                      className="text-button"
                      onClick={() => onNavigateLesson(item.lesson_id)}
                    >
                      Open Lesson
                    </button>
                  )}
                  {item.status !== "published" && (
                    <button
                      type="button"
                      className="text-button archive-action"
                      onClick={() => handleCancelScheduled(item.id)}
                    >
                      Cancel
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : selectedDate ? (
          <p className="empty-note">No lessons scheduled for this day.</p>
        ) : null}
      </div>

      {/* Schedule Modal */}
      {showScheduleModal && (
        <div className="modal-overlay" onClick={() => setShowScheduleModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
            <h3>Schedule a Lesson</h3>
            <p className="muted">Select an approved lesson and set the publication date and time.</p>
            <form onSubmit={handleScheduleSubmit}>
              <label className="field" style={{ marginBottom: "var(--space-4)" }}>
                <span>Select Lesson</span>
                <select
                  required
                  value={scheduleForm.lesson_id}
                  onChange={(e) => setScheduleForm({ ...scheduleForm, lesson_id: e.target.value })}
                  className="category-select"
                >
                  <option value="">Choose a lesson…</option>
                  {approvedLessons.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.course_title}: {l.title} ({l.status})
                    </option>
                  ))}
                </select>
              </label>

              <label className="field" style={{ marginBottom: "var(--space-4)" }}>
                <span>Publication Date & Time</span>
                <input
                  type="datetime-local"
                  required
                  value={scheduleForm.scheduled_at}
                  onChange={(e) => setScheduleForm({ ...scheduleForm, scheduled_at: e.target.value })}
                  className="search-input"
                />
              </label>

              <label className="field" style={{ marginBottom: "var(--space-6)" }}>
                <span>Custom Telegram Channel ID <small>Optional</small></span>
                <input
                  placeholder="@your_channel or -100xxxxxxxx"
                  value={scheduleForm.channel_id}
                  onChange={(e) => setScheduleForm({ ...scheduleForm, channel_id: e.target.value })}
                  className="search-input"
                />
              </label>

              <div className="modal-actions">
                <button type="button" className="secondary-button" onClick={() => setShowScheduleModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="publish-button" disabled={busy}>
                  Confirm Schedule
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}

