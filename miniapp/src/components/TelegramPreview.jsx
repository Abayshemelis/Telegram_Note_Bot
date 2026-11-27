import { useState, useMemo } from "react";
import {
  renderMarkdownToHtml,
  cleanTitle,
  estimateReadingStats,
} from "../utils/markdownRenderer";

export function TelegramPreview({
  courseTitle = "Course",
  lessonTitle = "Untitled Lesson",
  content = "",
  parts = [],
  onClose,
  publicMode = false,
  onOpenStudio = null,
}) {
  const [viewMode, setViewMode] = useState("pdf"); // 'pdf' | 'telegram'
  const [paperTheme, setPaperTheme] = useState("paper"); // 'paper' | 'dark'
  const [fontStyle, setFontStyle] = useState("serif"); // 'serif' | 'sans'
  const [copied, setCopied] = useState(false);

  const stats = useMemo(() => {
    return estimateReadingStats(content);
  }, [content]);

  const displayTitle = useMemo(() => {
    return cleanTitle(lessonTitle, content);
  }, [lessonTitle, content]);

  const renderedHtml = useMemo(() => {
    return renderMarkdownToHtml(content || "No lesson content to preview.");
  }, [content]);

  const handlePrint = () => {
    if (viewMode !== "pdf") {
      setViewMode("pdf");
      setTimeout(() => window.print(), 120);
    } else {
      window.print();
    }
  };

  const handleCopyText = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
    }
  };

  const todayStr = useMemo(() => {
    return new Date().toLocaleDateString("en-US", {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  }, []);

  return (
    <section className="preview-modal-container" role="dialog" aria-label="Lesson Preview">
      {/* Top Controls Bar */}
      <div className={`preview-navbar ${publicMode ? "preview-navbar-public" : ""}`}>
        <div className="preview-nav-left">
          <div className="preview-doc-badge">
            <span className="preview-badge-dot"></span>
            <span className="preview-doc-title" title={displayTitle}>
              {displayTitle}
            </span>
          </div>
          <span className="preview-course-tag">{courseTitle}</span>
        </div>

        {/* View Switcher: PDF vs Telegram (hidden in public student mode) */}
        {!publicMode && (
          <div className="preview-view-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={viewMode === "pdf"}
              className={`preview-tab-btn ${viewMode === "pdf" ? "active" : ""}`}
              onClick={() => setViewMode("pdf")}
            >
              <span className="preview-tab-icon">📄</span>
              <span>Academic PDF</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={viewMode === "telegram"}
              className={`preview-tab-btn ${viewMode === "telegram" ? "active" : ""}`}
              onClick={() => setViewMode("telegram")}
            >
              <span className="preview-tab-icon">📱</span>
              <span>Telegram Channel ({parts.length || 1})</span>
            </button>
          </div>
        )}

        {/* Right Actions */}
        <div className="preview-nav-right">
          {viewMode === "pdf" && (
            <>
              {/* Font toggle: Classic Serif vs Modern Sans */}
              <button
                type="button"
                className="preview-control-btn"
                onClick={() => setFontStyle((f) => (f === "serif" ? "sans" : "serif"))}
                title={fontStyle === "serif" ? "Switch to Modern Sans font" : "Switch to Classic Book Serif font"}
              >
                {fontStyle === "serif" ? "📖 Serif" : "⚡ Sans"}
              </button>

              {/* Theme toggle: Paper White vs Dark Sheet */}
              <button
                type="button"
                className="preview-control-btn"
                onClick={() => setPaperTheme((t) => (t === "paper" ? "dark" : "paper"))}
                title={paperTheme === "paper" ? "Switch to Dark Sheet Theme" : "Switch to Clean White Paper"}
              >
                {paperTheme === "paper" ? "🌙 Dark" : "☀️ Paper"}
              </button>

              {/* Print / Save as PDF */}
              <button
                type="button"
                className="preview-control-btn preview-print-btn"
                onClick={handlePrint}
                title="Print or Save as PDF"
              >
                🖨 PDF
              </button>
            </>
          )}

          <button
            type="button"
            className="preview-control-btn"
            onClick={handleCopyText}
            title="Copy raw markdown text"
          >
            {copied ? "✓ Copied" : "📋 Copy"}
          </button>

          {onOpenStudio && (
            <button
              type="button"
              className="preview-control-btn"
              onClick={onOpenStudio}
              title="Open CyberLearn Studio"
            >
              🛠 Studio
            </button>
          )}

          {!publicMode && onClose && (
            <button
              type="button"
              className="preview-close-btn"
              onClick={onClose}
              aria-label="Close preview"
              title="Close Preview (Esc)"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Main Preview Scrollport */}
      <div className="preview-scroll-viewport">
        {viewMode === "pdf" ? (
          /* =========================================================================
             STANDARDIZED ACADEMIC PDF DOCUMENT SHEET
             ========================================================================= */
          <div className={`pdf-viewer-canvas ${paperTheme === "paper" ? "theme-paper-white" : "theme-paper-dark"}`}>
            <article
              className={`pdf-page-sheet ${fontStyle === "serif" ? "font-academic-serif" : "font-modern-sans"}`}
              id="printable-pdf-document"
            >
              {/* PDF Running Header */}
              <div className="pdf-running-header">
                <span className="pdf-running-org">CYBERLEARN TECHNICAL INSTITUTE</span>
                <span className="pdf-running-docid">ACADEMIC COURSEWARE • REF: #{lessonTitle.toLowerCase().replace(/[^a-z0-9]/g, "").slice(0, 8) || "DOC"}</span>
              </div>

              {/* PDF Formal Masthead */}
              <header className="pdf-masthead">
                <div className="pdf-masthead-top">
                  <div className="pdf-brand-block">
                    <span className="pdf-brand-kicker">TECHNICAL SYLLABUS & LECTURE NOTES</span>
                    <span className="pdf-brand-subject">{courseTitle.toUpperCase()}</span>
                  </div>
                  <div className="pdf-classification-pill">OFFICIAL COURSEWARE</div>
                </div>

                <h1 className="pdf-doc-title">{displayTitle}</h1>
                {lessonTitle !== displayTitle && (
                  <div className="pdf-doc-slug">Identifier: <code>{lessonTitle}</code></div>
                )}

                {/* Metadata Strip */}
                <div className="pdf-meta-strip">
                  <div className="pdf-meta-cell">
                    <span className="pdf-meta-lbl">Date of Issue</span>
                    <span className="pdf-meta-txt">{todayStr}</span>
                  </div>
                  <div className="pdf-meta-cell">
                    <span className="pdf-meta-lbl">Reading Time</span>
                    <span className="pdf-meta-txt">~{stats.minutes} Minutes ({stats.words} words)</span>
                  </div>
                  <div className="pdf-meta-cell">
                    <span className="pdf-meta-lbl">Author / Source</span>
                    <span className="pdf-meta-txt">CyberLearn Academic Team</span>
                  </div>
                  <div className="pdf-meta-cell">
                    <span className="pdf-meta-lbl">Status</span>
                    <span className="pdf-meta-txt">Verified Reference</span>
                  </div>
                </div>

                {/* Academic Double Rule */}
                <div className="pdf-academic-double-rule">
                  <div className="pdf-rule-thick"></div>
                  <div className="pdf-rule-thin"></div>
                </div>
              </header>

              {/* PDF Document Body */}
              <section
                className="pdf-document-body"
                dangerouslySetInnerHTML={{ __html: renderedHtml }}
              />

              {/* PDF Document Footer */}
              <footer className="pdf-doc-footer">
                <div className="pdf-academic-double-rule" style={{ marginBottom: "12px" }}>
                  <div className="pdf-rule-thin"></div>
                  <div className="pdf-rule-thick"></div>
                </div>
                <div className="pdf-footer-content">
                  <span className="pdf-footer-left">
                    CyberLearn Studio Educational Courseware • Licensed for Academic & Practical Learning
                  </span>
                  <span className="pdf-footer-right">Page 1 of 1</span>
                </div>
              </footer>
            </article>
          </div>
        ) : (
          /* =========================================================================
             TELEGRAM CHANNEL SIMULATION VIEW
             ========================================================================= */
          <div className="telegram-preview-canvas">
            <div className="telegram-messages-container">
              {parts && parts.length > 0 ? (
                parts.map((part, index) => (
                  <article key={index} className="telegram-message-bubble">
                    <div
                      className="telegram-message-content"
                      dangerouslySetInnerHTML={{ __html: part }}
                    />
                    <div className="telegram-bubble-footer">
                      <span className="telegram-message-time">
                        {new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </span>
                      <span className="telegram-read-ticks">✓✓</span>
                    </div>
                  </article>
                ))
              ) : (
                <article className="telegram-message-bubble">
                  <div
                    className="telegram-message-content"
                    dangerouslySetInnerHTML={{
                      __html: renderMarkdownToHtml(content || "No lesson content to preview."),
                    }}
                  />
                  <div className="telegram-bubble-footer">
                    <span className="telegram-message-time">Just now</span>
                    <span className="telegram-read-ticks">✓✓</span>
                  </div>
                </article>
              )}

              {parts && parts.length > 1 && (
                <div className="telegram-continued-notice">
                  ℹ This lesson will be delivered across {parts.length} Telegram posts.
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
