import { useCallback, useEffect, useState } from "react";

export function CourseCategories({
  categories,
  onCreate,
  onUpdate,
  onDelete,
  editingCategoryId,
  setEditingCategoryId,
  editForm,
  setEditForm,
  busy,
  confirmAction,
}) {
  const [newCategory, setNewCategory] = useState({ name: "", description: "", color: "#4f46e5" });

  const handleCreate = async (event) => {
    event.preventDefault();
    if (!newCategory.name.trim()) return;
    await onCreate(newCategory.name.trim(), newCategory.description.trim(), newCategory.color);
    setNewCategory({ name: "", description: "", color: "#4f46e5" });
  };

  const handleUpdate = async (event) => {
    event.preventDefault();
    if (!editingCategoryId) return;
    await onUpdate(
      editingCategoryId,
      editForm.name.trim(),
      editForm.description.trim(),
      editForm.color
    );
    setEditingCategoryId(null);
    setEditForm({ name: "", description: "", color: "#4f46e5" });
  };

  const handleDelete = async (id) => {
    if (confirmAction) {
      const ok = await confirmAction({
        title: "Delete Category?",
        message: "Delete this category? Courses in this category will not be deleted.",
        confirmText: "Delete",
        danger: true,
      });
      if (!ok) return;
    }
    await onDelete(id);
  };

  const startEdit = (category) => {
    setEditingCategoryId(category.id);
    setEditForm({ name: category.name, description: category.description, color: category.color });
  };

  return (
    <section className="panel">
      <div className="panel-heading">
        <div><p className="eyebrow">CATEGORIES</p><h2>Organize Courses</h2></div>
      </div>

      <form className="course-form" onSubmit={handleCreate}>
        <input
          aria-label="New category name"
          placeholder="Category name"
          maxLength={60}
          value={newCategory.name}
          onChange={(event) => setNewCategory({ ...newCategory, name: event.target.value })}
          required
        />
        <input
          aria-label="Category color"
          placeholder="Color (hex)"
          maxLength={20}
          value={newCategory.color}
          onChange={(event) => setNewCategory({ ...newCategory, color: event.target.value })}
        />
        <button className="icon-button" disabled={busy} aria-label="Create category">+</button>
      </form>

      <div className="course-list">
        {categories.map((category) => (
          <div key={category.id} className="course-item category-item">
            <span
              className="course-icon"
              style={{ backgroundColor: category.color, color: "#ffffff" }}
            >
              {category.name[0]?.toUpperCase()}
            </span>
            <span className="course-text">
              <strong>{category.name}</strong>
              <small>{category.course_count} courses</small>
            </span>
            <div className="category-actions">
              {editingCategoryId === category.id ? (
                <form className="course-edit-form" onSubmit={handleUpdate} style={{ display: "contents" }}>
                  <input
                    aria-label="Category title"
                    maxLength={60}
                    required
                    value={editForm.name}
                    onChange={(event) => setEditForm({ ...editForm, name: event.target.value })}
                  />
                  <button className="secondary-button" disabled={busy}>Save</button>
                  <button
                    className="text-button"
                    type="button"
                    onClick={() => {
                      setEditingCategoryId(null);
                      setEditForm({ name: "", description: "", color: "#4f46e5" });
                    }}
                  >
                    Cancel
                  </button>
                </form>
              ) : (
                <>
                  <button className="text-button" onClick={() => startEdit(category)}>Edit</button>
                  <button className="text-button archive-action" onClick={() => handleDelete(category.id)}>
                    Delete
                  </button>
                </>
              )}
            </div>
          </div>
        ))}
        {!categories.length && <p className="empty-note">No categories yet. Create one to organize your courses.</p>}
      </div>
    </section>
  );
}
