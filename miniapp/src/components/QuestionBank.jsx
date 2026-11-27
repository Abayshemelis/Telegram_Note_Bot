import { useCallback, useEffect, useState } from "react";

export function QuestionBank({
  courseId,
  quizId,
  onQuestionAdded,
  busy,
  confirmAction,
}) {
  const [bankQuestions, setBankQuestions] = useState([]);
  const [showBank, setShowBank] = useState(false);

  const loadBank = useCallback(async () => {
    if (!courseId) return;
    const data = await fetch(
      `/api/question-bank?course_id=${courseId}`,
      {
        headers: {
          "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "",
        },
      },
    );
    if (!data.ok) return;
    setBankQuestions(await data.json());
  }, [courseId]);

  useEffect(() => {
    loadBank();
  }, [courseId, loadBank]);

  const addToQuiz = async (bankQuestion, position) => {
    if (!quizId) return;
    const response = await fetch("/api/question-bank/import", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "",
      },
      body: JSON.stringify({
        question_id: bankQuestion.id,
        quiz_id: quizId,
        position,
      }),
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || "Failed to import question.");
    }
    const quiz = await response.json();
    onQuestionAdded(quiz);
  };

  const saveToBank = async (question) => {
    if (!courseId) return;
    const response = await fetch("/api/question-bank", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "",
      },
      body: JSON.stringify({
        ...question,
        course_id: courseId,
      }),
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || "Failed to save to question bank.");
    }
    await loadBank();
    return response.json();
  };

  const deleteFromBank = async (id) => {
    if (confirmAction) {
      const ok = await confirmAction({
        title: "Remove Question?",
        message: "Remove this question from the bank?",
        confirmText: "Remove",
        danger: true,
      });
      if (!ok) return;
    }
    const response = await fetch(`/api/question-bank/${id}`, {
      method: "DELETE",
      headers: {
        "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData ?? "",
      },
    });
    if (!response.ok) return;
    await loadBank();
  };

  return (
    <>
      <button
        className="text-button"
        onClick={() => setShowBank((show) => !show)}
        disabled={busy || !courseId}
      >
        {showBank ? "Hide question bank" : "Question bank"}
      </button>

      {showBank && (
        <section className="question-bank-panel panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">QUESTION BANK</p>
              <h3>Reusable questions for this course</h3>
            </div>
            <button
              className="text-button"
              onClick={() => setShowBank(false)}
            >
              Close
            </button>
          </div>

          <div className="question-bank-list">
            {bankQuestions
              .filter((q) => ["multiple_choice", "true_false"].includes(q.question_type))
              .map((q) => (
              <div key={q.id} className="bank-question-item">
                <div className="bank-question-content">
                  <span className={`status status-${q.difficulty}`}>
                    {q.difficulty}
                  </span>
                  <span className="bank-question-type">
                    {q.question_type === "true_false" ? "True / False" : "Multiple Choice"}
                  </span>
                  <strong>{q.question_text}</strong>
                  {q.explanation && (
                    <p className="muted small">{q.explanation}</p>
                  )}
                </div>
                <div className="bank-question-actions">
                  <button
                    className="secondary-button"
                    onClick={() =>
                      addToQuiz(q, bankQuestions.length)
                        .then(() => setShowBank(false))
                        .catch((cause) => alert(cause.message))
                    }
                    disabled={busy || !quizId}
                  >
                    Add to quiz
                  </button>
                  <button
                    className="text-button archive-action"
                    onClick={() => deleteFromBank(q.id)}
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
            {!bankQuestions.length && (
              <p className="empty-note">
                No questions in the bank yet. Save questions from your quizzes
                here to reuse them across courses.
              </p>
            )}
          </div>
        </section>
      )}
    </>
  );
}
