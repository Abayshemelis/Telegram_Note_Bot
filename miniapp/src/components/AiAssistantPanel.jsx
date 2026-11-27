import { useCallback, useState } from "react";

const AI_GENERATION_TYPES = [
  { value: "structure_lesson", label: "Structure raw notes into a lesson" },
  { value: "improve_content", label: "Improve grammar and readability" },
  { value: "generate_examples", label: "Generate examples" },
  { value: "create_summary", label: "Create a summary" },
  { value: "extract_terms", label: "Extract key terms" },
  { value: "generate_learning_objectives", label: "Generate learning objectives" },
  { value: "generate_quiz_suggestions", label: "Suggest quiz questions" },
];

export function AiAssistantPanel({
  lesson,
  sourceContent,
  setSourceContent,
  content,
  setContent,
  busy,
}) {
  const [generationType, setGenerationType] = useState("structure_lesson");
  const [aiSourceText, setAiSourceText] = useState("");
  const [aiResult, setAiResult] = useState(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiError, setAiError] = useState("");
  const [aiNotice, setAiNotice] = useState("");

  const generateContent = useCallback(async () => {
    if (!lesson) return;
    const source = aiSourceText.trim() || sourceContent.trim();
    if (!source) {
      setAiError("Please add source material first.");
      return;
    }
    setAiBusy(true);
    setAiError("");
    setAiNotice("");
    try {
      const result = await fetch("/api/ai/generate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "",
        },
        body: JSON.stringify({
          lesson_id: lesson.id,
          source_text: source,
          generation_type: generationType,
        }),
      });
      if (!result.ok) {
        const errorData = await result.json().catch(() => ({}));
        throw new Error(errorData.detail || "AI generation failed.");
      }
      const data = await result.json();
      setAiResult(data);
      setAiNotice("AI generated content. Review and apply it below.");
    } catch (cause) {
      setAiError(cause.message || "AI generation failed.");
    } finally {
      setAiBusy(false);
    }
  }, [lesson, generationType, aiSourceText, sourceContent]);

  const applyToContent = useCallback(() => {
    if (!aiResult?.generated_content) return;
    setContent(aiResult.generated_content);
    setAiNotice("AI content applied to lesson draft. Save when ready.");
  }, [aiResult, setContent]);

  const applyToSource = useCallback(() => {
    if (!aiResult?.generated_content) return;
    setSourceContent(aiResult.generated_content);
    setAiNotice("AI content applied to source material. Save when ready.");
  }, [aiResult, setSourceContent, setAiNotice]);

  const reject = useCallback(() => {
    setAiResult(null);
    setAiError("");
    setAiNotice("");
  }, []);

  return (
    <section className="panel ai-assistant-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">AI CONTENT STUDIO</p>
          <h2>AI Assistant</h2>
        </div>
      </div>

      {aiError && (
        <div className="toast toast-error">
          {aiError}
          <button onClick={() => setAiError("")} aria-label="Dismiss">×</button>
        </div>
      )}

      <div className="ai-generation-controls">
        <label className="field">
          <span>Generation type</span>
          <select
            value={generationType}
            onChange={(event) => setGenerationType(event.target.value)}
            className="category-select"
          >
            {AI_GENERATION_TYPES.map((type) => (
              <option key={type.value} value={type.value}>
                {type.label}
              </option>
            ))}
          </select>
        </label>
        <button
          className="secondary-button"
          disabled={busy || aiBusy || !lesson}
          onClick={generateContent}
        >
          {aiBusy ? "Generating…" : "Generate with AI"}
        </button>
      </div>

      <div className="ai-source-section">
        <label className="field">
          <span>Source text <small>Uses lesson source material if left blank</small></span>
          <textarea
            rows={4}
            placeholder="Paste raw notes or text to process with AI..."
            value={aiSourceText}
            onChange={(event) => setAiSourceText(event.target.value)}
          />
        </label>
      </div>

      {aiResult && (
        <>
          <div className="ai-result-section">
            <label className="field">
              <span>AI-generated content <small>Review before applying</small></span>
              <textarea
                rows={10}
                readOnly
                value={aiResult.generated_content}
              />
            </label>
            <div className="ai-actions">
              <button
                className="secondary-button"
                onClick={applyToContent}
                disabled={busy}
              >
                Apply to lesson content
              </button>
              <button
                className="ghost-button"
                onClick={applyToSource}
                disabled={busy}
              >
                Apply to source material
              </button>
              <button
                className="text-button archive-action"
                onClick={reject}
              >
                Reject
              </button>
            </div>
          </div>
          {aiNotice && (
            <div className="toast toast-success">
              {aiNotice}
              <button onClick={() => setAiNotice("")} aria-label="Dismiss">×</button>
            </div>
          )}
        </>
      )}

      <p className="muted small">
        AI-generated content is stored separately from your original notes. You must
        explicitly apply it to the lesson draft and save before it becomes part of
        the lesson. Original source material is never modified by AI.
      </p>
    </section>
  );
}
