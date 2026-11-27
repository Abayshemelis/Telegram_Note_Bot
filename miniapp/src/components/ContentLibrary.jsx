import { useCallback, useEffect, useState } from "react";

export function ContentLibrary({ busy }) {
  const [query, setQuery] = useState("");
  const [courseFilter, setCourseFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [courses, setCourses] = useState([]);
  const [lessons, setLessons] = useState([]);
  const [loading, setLoading] = useState(false);

  const STATUS_OPTIONS = [
    { value: "all", label: "All statuses" },
    { value: "draft", label: "Draft" },
    { value: "approved", label: "Approved" },
    { value: "published", label: "Published" },
    { value: "failed", label: "Failed" },
    { value: "publishing", label: "Publishing" },
  ];

  const loadCourses = useCallback(async () => {
    const data = await fetch("/api/courses?include_archived=true", {
      headers: {
        "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "",
      },
    });
    if (data.ok) setCourses(await data.json());
  }, []);

  const searchLessons = useCallback(async () => {
    setLoading(true);
    try {
      let url = `/api/courses/1/lessons?query=${encodeURIComponent(query)}`;
      const data = await fetch(url, {
        headers: {
          "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "",
        },
      });
      if (data.ok) {
        let results = await data.json();
        if (statusFilter !== "all") {
          results = results.filter((l) => l.status === statusFilter);
        }
        setLessons(results);
      }
    } finally {
      setLoading(false);
    }
  }, [query, statusFilter]);

  useEffect(() => {
    loadCourses();
  }, [loadCourses]);

  useEffect(() => {
    const timer = setTimeout(searchLessons, 300);
    return () => clearTimeout(timer);
  }, [query, courseFilter, statusFilter, searchLessons]);

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">CONTENT LIBRARY</p>
          <h2>All Lessons</h2>
        </div>
      </div>

      <div className="course-filters">
        <input
          aria-label="Search all lessons"
          placeholder="Search lessons by title or content..."
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="search-input"
        />
        <select
          aria-label="Filter by status"
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value)}
          className="category-select"
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </div>

      {loading ? (
        <div className="empty-state" style={{ justifyContent: "center" }}>
          <p className="muted">Searching lessons…</p>
        </div>
      ) : lessons.length > 0 ? (
        <div className="course-grid">
          {lessons.map((lesson) => (
            <div key={lesson.id} className="course-card">
              <div className="course-card-header">
                <span className="course-badge">📄</span>
                <span
                  className={`status status-${lesson.status}`}
                >
                  {lesson.status}
                </span>
              </div>
              <div className="course-card-body">
                <h3>{lesson.title}</h3>
                <p className="course-description">
                  Course: {lesson.course_title || "Unknown"}
                </p>
                <div className="course-meta">
                  <span>Updated {new Date(lesson.updated_at).toLocaleDateString()}</span>
                </div>
              </div>
              <div className="course-card-actions">
                <button className="secondary-button">Open</button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <div className="empty-art">📄</div>
          <h3>No lessons found</h3>
          <p className="muted">Try adjusting your search or status filter.</p>
        </div>
      )}
    </section>
  );
}
