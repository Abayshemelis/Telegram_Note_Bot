import { useRef, useEffect } from "react";

export function FormattingToolbar({
  onFormat,
  onStandardize,
  onUploadImage,
  imageUploading = false,
  activeFormat,
  linkDialog,
  onCloseLink,
  onSubmitLink,
  onLinkDialogChange,
}) {
  const urlInputRef = useRef(null);
  const textInputRef = useRef(null);
  const imageInputRef = useRef(null);

  useEffect(() => {
    if (linkDialog?.isOpen) {
      if (linkDialog.text) {
        urlInputRef.current?.focus();
        urlInputRef.current?.select();
      } else {
        textInputRef.current?.focus();
      }
    }
  }, [linkDialog?.isOpen]);

  const buttons = [
    {
      format: "bold",
      title: "Bold (Ctrl+B)",
      icon: (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M6 12h9a4 4 0 0 1 0 8H7a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h7a4 4 0 0 1 0 8" />
        </svg>
      ),
      label: "Bold",
    },
    {
      format: "italic",
      title: "Italic (Ctrl+I)",
      icon: (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <line x1="19" x2="10" y1="4" y2="4" />
          <line x1="14" x2="5" y1="20" y2="20" />
          <line x1="15" x2="9" y1="4" y2="20" />
        </svg>
      ),
      label: "Italic",
    },
    {
      format: "heading",
      title: "Section Heading (## )",
      icon: (
        <span style={{ fontWeight: 700, fontSize: "13px", letterSpacing: "-0.05em" }} aria-hidden="true">
          H2
        </span>
      ),
      label: "Heading",
    },
    {
      format: "bullet",
      title: "Bullet List (- )",
      icon: (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <line x1="9" x2="20" y1="6" y2="6" />
          <line x1="9" x2="20" y1="12" y2="12" />
          <line x1="9" x2="20" y1="18" y2="18" />
          <circle cx="4" cy="6" r="2" fill="currentColor" />
          <circle cx="4" cy="12" r="2" fill="currentColor" />
          <circle cx="4" cy="18" r="2" fill="currentColor" />
        </svg>
      ),
      label: "Bullet list",
    },
    {
      format: "numbered",
      title: "Numbered List (1. )",
      icon: (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <line x1="10" x2="21" y1="6" y2="6" />
          <line x1="10" x2="21" y1="12" y2="12" />
          <line x1="10" x2="21" y1="18" y2="18" />
          <path d="M4 6h1v4" />
          <path d="M4 10h2" />
          <path d="M6 18H4c0-1 2-2 2-3s-1-1.5-2-1" />
        </svg>
      ),
      label: "Numbered list",
    },
    {
      format: "quote",
      title: "Blockquote (> )",
      icon: (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M3 21c3 0 7-1 7-8V5c0-1.25-.756-2.017-2-2H4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2 1 0 1 0 1 1v1c0 1-1 2-2 2s-1 .008-1 1.031V20c0 1 0 1 1 1z" />
          <path d="M15 21c3 0 7-1 7-8V5c0-1.25-.757-2.017-2-2h-4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2 1 0 1 0 1 1v1c0 1-1 2-2 2s-1 .008-1 1.031V20c0 1 0 1 1 1z" />
        </svg>
      ),
      label: "Quote",
    },
    {
      format: "inline-code",
      title: "Inline Code (`code`) (Ctrl+E)",
      icon: (
        <span style={{ fontFamily: "monospace", fontWeight: 600, fontSize: "13px" }} aria-hidden="true">
          `c`
        </span>
      ),
      label: "Inline code",
    },
    {
      format: "code",
      title: "Code Block (```)",
      icon: (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <polyline points="16 18 22 12 16 6" />
          <polyline points="8 6 2 12 8 18" />
        </svg>
      ),
      label: "Code block",
    },
    {
      format: "link",
      title: "Insert Link ([text](url)) (Ctrl+K)",
      icon: (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
        </svg>
      ),
      label: "Link",
    },
  ];

  const handleInputKeyDown = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      if (onSubmitLink && linkDialog) {
        onSubmitLink(linkDialog.text, linkDialog.url, linkDialog.start, linkDialog.end);
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      if (onCloseLink) onCloseLink();
    }
  };

  return (
    <div className="formatting-toolbar-wrapper">
      <div className="formatting-toolbar" role="toolbar" aria-label="Text formatting">
        {buttons.map((button) => {
          const isActive =
            activeFormat === button.format || (button.format === "link" && linkDialog?.isOpen);
          return (
            <button
              key={button.format}
              type="button"
              className={`format-button ${isActive ? "format-button-active" : ""}`}
              title={button.title}
              aria-label={button.label}
              onMouseDown={(e) => {
                // Prevent focus theft so textarea selection is preserved
                e.preventDefault();
              }}
              onClick={() => onFormat(button.format)}
            >
              {button.icon}
            </button>
          );
        })}
        {onUploadImage && (
          <>
            <input
              id="lesson-image-file-input"
              ref={imageInputRef}
              type="file"
              accept="image/*"
              style={{ display: "none" }}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) {
                  onUploadImage(file);
                }
                e.target.value = "";
              }}
            />
            <label
              htmlFor="lesson-image-file-input"
              className="format-button"
              style={{
                width: "auto",
                padding: "0 8px",
                fontSize: "12px",
                gap: "4px",
                display: "inline-flex",
                alignItems: "center",
                cursor: imageUploading ? "wait" : "pointer",
                opacity: imageUploading ? 0.6 : 1,
                pointerEvents: imageUploading ? "none" : "auto",
              }}
              title="Insert Image (or Paste Ctrl+V directly in lesson)"
              aria-label="Insert Image"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <rect width="18" height="18" x="3" y="3" rx="2" ry="2" />
                <circle cx="9" cy="9" r="2" />
                <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />
              </svg>
              <span style={{ fontWeight: 600 }}>{imageUploading ? "Uploading..." : "Image"}</span>
            </label>
          </>
        )}
        {onStandardize && (
          <>
            <div
              className="formatting-toolbar-divider"
              style={{
                width: "1px",
                height: "18px",
                backgroundColor: "var(--border-subtle, rgba(255, 255, 255, 0.15))",
                margin: "0 4px",
              }}
            />
            <button
              type="button"
              className="format-button"
              style={{
                width: "auto",
                padding: "0 8px",
                fontSize: "12px",
                gap: "4px",
                display: "inline-flex",
                alignItems: "center",
              }}
              title="Standardize Academic Style (Auto-format paragraphs, headings, code blocks & callouts)"
              aria-label="Standardize Academic Style"
              onMouseDown={(e) => {
                e.preventDefault();
              }}
              onClick={onStandardize}
            >
              <span aria-hidden="true">🪄</span>
              <span style={{ fontWeight: 600 }}>Standardize</span>
            </button>
          </>
        )}
      </div>

      {linkDialog?.isOpen && (
        <div className="link-popover-card" role="dialog" aria-label="Insert Link">
          <div className="link-popover-header">
            <span className="link-popover-title">Insert Link</span>
            <button
              type="button"
              className="link-popover-close-btn"
              onClick={onCloseLink}
              aria-label="Close"
              title="Close (Esc)"
            >
              ✕
            </button>
          </div>
          <div className="link-popover-body">
            <div className="link-popover-row">
              <label htmlFor="toolbar-link-text">Text</label>
              <input
                id="toolbar-link-text"
                ref={textInputRef}
                type="text"
                className="link-popover-input"
                value={linkDialog.text || ""}
                onChange={(e) => onLinkDialogChange?.("text", e.target.value)}
                onKeyDown={handleInputKeyDown}
                placeholder="Display text"
              />
            </div>
            <div className="link-popover-row">
              <label htmlFor="toolbar-link-url">URL</label>
              <input
                id="toolbar-link-url"
                ref={urlInputRef}
                type="text"
                className="link-popover-input"
                value={linkDialog.url || ""}
                onChange={(e) => onLinkDialogChange?.("url", e.target.value)}
                onKeyDown={handleInputKeyDown}
                placeholder="https://example.com"
              />
            </div>
          </div>
          <div className="link-popover-footer">
            <button
              type="button"
              className="btn btn-secondary btn-xs"
              onClick={onCloseLink}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-primary btn-xs"
              onClick={() =>
                onSubmitLink?.(linkDialog.text, linkDialog.url, linkDialog.start, linkDialog.end)
              }
            >
              Insert
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
