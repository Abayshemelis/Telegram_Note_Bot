import { useState } from "react";
import { CourseCard } from "./CourseCard";

export function CourseListPage({
  courses,
  categories,
  onSelectCourse,
  onEditCourse,
  onArchiveCourse,
  onDeleteCourse,
  busy,
}) {
  const [searchQuery, setSearchQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [courseToDelete, setCourseToDelete] = useState(null);

  const filteredCourses = courses.filter((course) => {
    const matchesSearch = course.title
      .toLowerCase()
      .includes(searchQuery.toLowerCase());
    const matchesCategory =
      categoryFilter === "all" || course.category_id === Number(categoryFilter);
    return matchesSearch && matchesCategory;
  });

  const handleDeleteClick = (course) => {
    setCourseToDelete(course);
    setShowDeleteDialog(true);
  };

  const handleConfirmDelete = async () => {
    if (!courseToDelete) return;
    await onDeleteCourse(courseToDelete.id);
    setCourseToDelete(null);
    setShowDeleteDialog(false);
  };

  const handleCancelDelete = () => {
    setCourseToDelete(null);
    setShowDeleteDialog(false);
  };

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">COURSE DIRECTORY</p>
          <h2>All Courses</h2>
        </div>
        <div className="course-filters">
          <input
            aria-label="Search courses"
            placeholder="Filter courses by title…"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            className="search-input"
          />
          <select
            aria-label="Filter by category"
            value={categoryFilter}
            onChange={(event) => setCategoryFilter(event.target.value)}
            className="category-select"
          >
            <option value="all">All categories</option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="course-grid">
        {filteredCourses.map((course) => (
          <CourseCard
            key={course.id}
            course={course}
            onSelect={() => onSelectCourse && onSelectCourse(course.id)}
            onEdit={() => onEditCourse && onEditCourse(course)}
            onArchive={(id, isArchived) => onArchiveCourse && onArchiveCourse(id, isArchived)}
            onDelete={() => handleDeleteClick(course)}
            busy={busy}
          />
        ))}
        {!filteredCourses.length && (
          <div className="empty-state">
            <div className="empty-art">◈</div>
            <h3>No courses found</h3>
            <p className="muted">Try adjusting your search query or category filter.</p>
          </div>
        )}
      </div>

      {showDeleteDialog && courseToDelete && (
        <div className="modal-overlay" onClick={handleCancelDelete}>
          <div className="modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
            <h3>Delete "{courseToDelete.title}"?</h3>
            <p className="muted">
              Are you sure you want to delete this course? Courses with active lessons cannot be deleted without first archiving them or removing lessons.
            </p>
            <div className="modal-actions">
              <button type="button" className="secondary-button" onClick={handleCancelDelete}>
                Cancel
              </button>
              <button type="button" className="archive-action" onClick={handleConfirmDelete} disabled={busy}>
                Confirm Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
