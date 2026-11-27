export function CourseCard({ course, onSelect, onEdit, onArchive, onDelete, busy }) {
  return (
    <article className="course-card">
      <div className="course-card-header">
        <div className="course-badge" style={{ backgroundColor: course.category_color || "#4f46e5" }}>
          {course.category_name?.[0]?.toUpperCase() || "C"}
        </div>
        <span
          className={`status status-${course.is_archived ? "archived" : "active"}`}
        >
          {course.is_archived ? "Archived" : "Active"}
        </span>
      </div>
      <div className="course-card-body">
        <h3>{course.title}</h3>
        {course.description && <p className="course-description">{course.description}</p>}
        <div className="course-meta">
          <span>{course.lesson_count} lessons</span>
          <span>{course.difficulty || "—"}</span>
          <span>{course.estimated_duration || "—"}</span>
        </div>
      </div>
      <div className="course-card-actions">
        <button className="secondary-button" onClick={() => onSelect(course.id)}>
          Open
        </button>
        <button className="text-button" onClick={() => onEdit(course)}>
          Edit
        </button>
        <button
          className="text-button archive-action"
          onClick={() => (course.is_archived ? onArchive(course.id, false) : onArchive(course.id, true))}
          disabled={busy}
        >
          {course.is_archived ? "Restore" : "Archive"}
        </button>
        <button className="text-button archive-action" onClick={() => onDelete(course)}>
          Delete
        </button>
      </div>
    </article>
  );
}
