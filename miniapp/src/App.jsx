import { useCallback, useEffect, useRef, useState } from "react";
import { SearchableSelect } from "./components/SearchableSelect";
import { ThemeToggle } from "./components/ThemeToggle";
import { Toast } from "./components/Toast";
import { AuthScreen } from "./components/AuthScreen";
import { Dashboard } from "./components/Dashboard";
import { CourseCategories } from "./components/CourseCategories";
import { CourseListPage } from "./components/CourseListPage";
import { CourseCard } from "./components/CourseCard";
import { AiAssistantPanel } from "./components/AiAssistantPanel";
import { FormattingToolbar } from "./components/FormattingToolbar";
import {
  applyInlineFormat,
  applyLinePrefix,
  applyNumberedList,
  applyCodeBlock,
  applyLink,
  handleSmartEnter,
  handleTab,
  detectActiveFormat,
} from "./utils/markdownEditor";
import { TelegramPreview } from "./components/TelegramPreview";
import { smartFormatAcademicText, cleanTitle } from "./utils/markdownRenderer";
import { QuestionBank } from "./components/QuestionBank";
import { PublishingCalendar } from "./components/PublishingCalendar";
import { PublishingManager } from "./components/PublishingManager";
import { SettingsPage } from "./components/SettingsPage";

const EMPTY_COURSE = { title: "", description: "" };
const QUIZ_DIFFICULTIES = ["easy", "medium", "hard"];
const DIFFICULTY_OPTIONS = QUIZ_DIFFICULTIES.map((difficulty) => ({
  value: difficulty,
  label: difficulty[0].toUpperCase() + difficulty.slice(1),
}));
const QUESTION_TYPES = [
  ["multiple_choice", "Multiple choice"],
  ["true_false", "True / false"],
];

function comparableQuiz(quiz) {
  if (!quiz) return null;
  return {
    title: (quiz.title ?? "").trim(),
    instructions: (quiz.instructions ?? "").trim(),
    difficulty: quiz.difficulty ?? "medium",
    duration_minutes: quiz.duration_minutes ? Number(quiz.duration_minutes) : null,
    questions: (quiz.questions || []).map((question) => ({
      question_type: question.question_type,
      question_text: (question.question_text ?? "").trim(),
      explanation: (question.explanation ?? "").trim(),
      difficulty: question.difficulty ?? "medium",
      options: (question.options || []).map((option) => ({
        option_text: (option.option_text ?? "").trim(),
        match_text: (option.match_text ?? "").trim() || null,
        is_correct: Boolean(option.is_correct),
      })),
    })),
  };
}

export function getTelegramInitData() {
  if (window.Telegram?.WebApp?.initData) {
    return window.Telegram.WebApp.initData;
  }
  if (typeof window !== "undefined" && window.location.hash) {
    try {
      const hash = window.location.hash.replace(/^#/, "");
      const params = new URLSearchParams(hash);
      if (params.has("tgWebAppData")) {
        return params.get("tgWebAppData") || "";
      }
    } catch (e) {
      // ignore
    }
  }
  return "";
}

export function isInsideTelegram() {
  if (typeof window === "undefined") return false;
  try {
    if (window.TelegramWebviewProxy || window.TelegramGameProxy) return true;
    if (window.webkit?.messageHandlers?.webApp) return true;
    if (getTelegramInitData()) return true;
    const tg = window.Telegram?.WebApp;
    if (!tg) return false;
    if (tg.platform && tg.platform !== "unknown") return true;
    if (tg.version && tg.version !== "") return true;
    if (tg.initDataUnsafe && Object.keys(tg.initDataUnsafe).length > 0) return true;
    if (tg.themeParams && Object.keys(tg.themeParams).length > 0) return true;
    if (window.location.hash.includes("tgWebAppData") || window.location.search.includes("tgWebAppData")) return true;
    if (window.location.hash.includes("tgThemeParams") || window.location.search.includes("tgThemeParams")) return true;
    if (typeof navigator !== "undefined" && navigator.userAgent && /Telegram/i.test(navigator.userAgent)) return true;
  } catch (e) { }
  return false;
}

async function api(path, options = {}) {
  const initData = getTelegramInitData();
  const { timeoutMs = 30000, ...fetchOptions } = options;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(path, {
      signal: controller.signal,
      ...fetchOptions,
      headers: {
        "Content-Type": "application/json",
        "X-Telegram-Init-Data": initData,
        ...fetchOptions.headers,
      },
    });
    clearTimeout(timeoutId);
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = Array.isArray(result.detail)
        ? result.detail.map((item) => item.msg).join(" ")
        : result.detail;
      throw new Error(detail || `Request failed (${response.status})`);
    }
    return result;
  } catch (err) {
    clearTimeout(timeoutId);
    if (err.name === "AbortError") {
      throw new Error("Request timed out. The server may be waking up — please try again in a moment.");
    }
    throw err;
  }
}

function App() {
  const [admin, setAdmin] = useState(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [lessonError, setLessonError] = useState(null);
  const [viewMode, setViewMode] = useState("lessons");
  const [coursesTab, setCoursesTab] = useState("courses");
  const [mobileEditorTab, setMobileEditorTab] = useState("draft");
  const [dashboard, setDashboard] = useState(null);
  const [courses, setCourses] = useState([]);
  const [categories, setCategories] = useState([]);
  const [editingCategory, setEditingCategory] = useState(null);
  const [categoryEditForm, setCategoryEditForm] = useState({
    name: "",
    description: "",
    color: "#4f46e5",
  });
  const [courseId, setCourseId] = useState("");
  const [showArchivedCourses, setShowArchivedCourses] = useState(false);
  const [editingCourse, setEditingCourse] = useState(false);
  const [courseEditForm, setCourseEditForm] = useState(EMPTY_COURSE);
  const [courseMenuOpen, setCourseMenuOpen] = useState(false);
  const courseMenuRef = useRef(null);
  const [lessons, setLessons] = useState([]);
  const [quizzes, setQuizzes] = useState([]);
  const [quiz, setQuiz] = useState(null);
  const [quizVersions, setQuizVersions] = useState([]);
  const [quizTitle, setQuizTitle] = useState("");
  const [quizInstructions, setQuizInstructions] = useState("");
  const [quizDifficulty, setQuizDifficulty] = useState("medium");
  const [quizDuration, setQuizDuration] = useState("");
  const [quizQuestions, setQuizQuestions] = useState([]);
  const [newQuestionType, setNewQuestionType] = useState("multiple_choice");
  const [quizPreviewOpen, setQuizPreviewOpen] = useState(false);
  const [lessonQuery, setLessonQuery] = useState("");
  const [lesson, setLesson] = useState(null);
  const [versions, setVersions] = useState([]);
  const [noteImportOpen, setNoteImportOpen] = useState(false);
  const [questionBankOpen, setQuestionBankOpen] = useState(false);
  const [noteQuery, setNoteQuery] = useState("");
  const [botNotes, setBotNotes] = useState([]);
  const [courseForm, setCourseForm] = useState(EMPTY_COURSE);
  const [showNewCourseForm, setShowNewCourseForm] = useState(false);
  const [lessonTitle, setLessonTitle] = useState("");
  const [sourceContent, setSourceContent] = useState("");
  const [content, setContent] = useState("");
  const [preview, setPreview] = useState([]);
  const [showTelegramPreview, setShowTelegramPreview] = useState(false);
  const [publicLesson, setPublicLesson] = useState(null);
  const [formattingActive, setFormattingActive] = useState(null);
  const [linkDialog, setLinkDialog] = useState(null);
  const [aiPanelOpen, setAiPanelOpen] = useState(false);
  const [lastSavedTime, setLastSavedTime] = useState(null);
  const contentRef = useRef(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [imageUploading, setImageUploading] = useState(false);
  const wantsFullscreenRef = useRef(true);
  const editorHistoryRef = useRef({ past: [], future: [], lastTypedAt: 0 });
  const [historyStatus, setHistoryStatus] = useState({ canUndo: false, canRedo: false });
  const [confirmDialog, setConfirmDialog] = useState(null);
  const [isFullscreen, setIsFullscreen] = useState(() => {
    return Boolean(window.Telegram?.WebApp?.isFullscreen);
  });
  const selectedCourse = courses.find((course) => String(course.id) === courseId);
  const visibleCourses = courses.filter(
    (course) => showArchivedCourses || !course.is_archived,
  );
  const normalizeText = (text) => (text ?? "").replace(/\r\n/g, "\n").trim();
  const hasUnsavedChanges = Boolean(
    lesson &&
    (normalizeText(lessonTitle) !== normalizeText(lesson.title) ||
      normalizeText(sourceContent) !== normalizeText(lesson.source_content) ||
      normalizeText(content) !== normalizeText(lesson.content)),
  );
  const quizDraft = quiz && {
    title: quizTitle,
    instructions: quizInstructions,
    difficulty: quizDifficulty,
    duration_minutes: quizDuration ? Number(quizDuration) : null,
    questions: quizQuestions.map((question) => ({
      question_type: question.question_type,
      question_text: question.question_text,
      explanation: question.explanation,
      difficulty: question.difficulty,
      options: question.options.map((option) => ({
        option_text: option.option_text,
        match_text: option.match_text ?? null,
        is_correct: option.is_correct,
      })),
    })),
  };
  const hasUnsavedQuizChanges = Boolean(
    quiz &&
    JSON.stringify(comparableQuiz(quizDraft)) !==
    JSON.stringify(comparableQuiz(quiz)),
  );
  const latestSnapshotMatchesDraft = Boolean(
    quiz?.latest_version &&
    JSON.stringify(comparableQuiz(quizDraft)) ===
    JSON.stringify(comparableQuiz(quiz.latest_version.snapshot)),
  );
  const approvedSnapshotMatchesDraft = Boolean(
    quiz?.latest_version?.status === "approved" &&
    latestSnapshotMatchesDraft &&
    !hasUnsavedQuizChanges,
  );

  const loadDashboard = useCallback(async () => {
    setDashboard(await api("/api/dashboard"));
  }, []);

  const loadCourses = useCallback(async () => {
    const data = await api("/api/courses?include_archived=true");
    setCourses(data);
    if (!courseId && data.length) {
      const firstActive = data.find((course) => !course.is_archived) || data[0];
      setCourseId(String(firstActive.id));
    }
  }, [courseId]);

  const loadCategories = useCallback(async () => {
    setCategories(await api("/api/course-categories"));
  }, []);

  const createCategory = useCallback(
    async (name, description, color) => {
      return await api("/api/course-categories", {
        method: "POST",
        body: JSON.stringify({ name, description, color }),
      });
    },
    [],
  );

  const updateCategory = useCallback(
    async (id, name, description, color) => {
      return await api(`/api/course-categories/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ name, description, color }),
      });
    },
    [],
  );

  const deleteCategory = useCallback(
    async (id) => {
      return await api(`/api/course-categories/${id}`, {
        method: "DELETE",
      });
    },
    [],
  );

  const apiCreateCourse = useCallback(
    async (title, description, categoryId) => {
      return await api("/api/courses", {
        method: "POST",
        body: JSON.stringify({ title, description, category_id: categoryId || null }),
      });
    },
    [],
  );

  const apiUpdateCourse = useCallback(
    async (id, title, description, categoryId) => {
      return await api(`/api/courses/${id}`, {
        method: "PUT",
        body: JSON.stringify({ title, description, category_id: categoryId || null }),
      });
    },
    [],
  );

  const apiArchiveCourse = useCallback(
    async (id, isArchived) => {
      return await api(`/api/courses/${id}/archive`, {
        method: "PATCH",
        body: JSON.stringify({ is_archived: isArchived }),
      });
    },
    [],
  );

  const apiDeleteCourse = useCallback(
    async (id) => {
      return await api(`/api/courses/${id}`, {
        method: "DELETE",
      });
    },
    [],
  );

  const loadLessons = useCallback(async (id, query = "") => {
    if (!id) {
      setLessons([]);
      return;
    }
    setLessons(
      await api(
        `/api/courses/${id}/lessons?query=${encodeURIComponent(query)}`,
      ),
    );
  }, []);

  const loadQuizzes = useCallback(async (id) => {
    if (!id) {
      setQuizzes([]);
      return;
    }
    setQuizzes(await api(`/api/courses/${id}/quizzes`));
  }, []);

  const loadQuiz = useCallback(async (id) => {
    const [data, history] = await Promise.all([
      api(`/api/quizzes/${id}`),
      api(`/api/quizzes/${id}/versions`),
    ]);
    const sanitized = (data.questions ?? []).map((q) => {
      if (!["multiple_choice", "true_false"].includes(q.question_type)) {
        return {
          ...q,
          question_type: "multiple_choice",
          options: (q.options ?? []).map((opt) => ({
            option_text: opt.option_text ?? "",
            match_text: null,
            is_correct: Boolean(opt.is_correct),
          })),
        };
      }
      return q;
    });
    setQuiz(data);
    setQuizTitle(data.title ?? "");
    setQuizInstructions(data.instructions ?? "");
    setQuizDifficulty(data.difficulty ?? "medium");
    setQuizDuration(data.duration_minutes ? String(data.duration_minutes) : "");
    setQuizQuestions(sanitized);
    setQuizVersions(history ?? []);
    setQuizPreviewOpen(false);
  }, []);

  const loadLesson = useCallback(async (id) => {
    if (!id) return;
    const [data, history] = await Promise.all([
      api(`/api/lessons/${id}`),
      api(`/api/lessons/${id}/versions`),
    ]);
    setLesson(data);
    setLessonTitle(data.title ?? "");
    setSourceContent(data.source_content ?? "");
    setContent(data.content ?? "");
    setVersions(history ?? []);
    setPreview([]);
    setEditingCourse(false);
  }, []);

  const confirmAction = useCallback(
    ({
      title = "Confirm Action",
      message = "Are you sure you want to continue?",
      confirmText = "Confirm",
      cancelText = "Cancel",
      danger = false,
    }) => {
      return new Promise((resolve) => {
        try {
          if (danger) {
            window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.("warning");
          } else {
            window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.("light");
          }
        } catch (e) { }

        setConfirmDialog({
          title,
          message,
          confirmText,
          cancelText,
          danger,
          onConfirm: () => {
            setConfirmDialog(null);
            resolve(true);
          },
          onCancel: () => {
            setConfirmDialog(null);
            resolve(false);
          },
        });
      });
    },
    [],
  );

  useEffect(() => {
    if (!confirmDialog) return;
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        confirmDialog.onCancel();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [confirmDialog]);

  const confirmDiscardChanges = useCallback(async () => {
    if (!hasUnsavedChanges) return true;
    return await confirmAction({
      title: "Discard Lesson Changes?",
      message: "You have unsaved changes in this lesson. Leave and discard them?",
      confirmText: "Discard",
      cancelText: "Keep Editing",
      danger: true,
    });
  }, [hasUnsavedChanges, confirmAction]);

  const confirmDiscardQuizChanges = useCallback(async () => {
    if (!hasUnsavedQuizChanges) return true;
    return await confirmAction({
      title: "Discard Quiz Changes?",
      message: "You have unsaved quiz changes. Leave this quiz and discard them?",
      confirmText: "Discard",
      cancelText: "Keep Editing",
      danger: true,
    });
  }, [hasUnsavedQuizChanges, confirmAction]);

  useEffect(() => {
    let active = true;

    // Hard safety timer: ensure initialLoading NEVER hangs permanently (max 3.5 seconds)
    const safetyTimer = setTimeout(() => {
      if (active) {
        setInitialLoading(false);
      }
    }, 3500);

    // Check if URL has a deep link to a specific lesson (#lesson-123 or ?lesson=123)
    const searchParams = new URLSearchParams(window.location.search);
    const qLesson = searchParams.get("lesson");
    const hash = window.location.hash || "";
    const hashMatch = hash.match(/lesson[-_](\d+)/);
    const targetId = (qLesson && /^\d+$/.test(qLesson)) ? qLesson : (hashMatch ? hashMatch[1] : null);

    const checkPublicLesson = () => {
      if (typeof window === "undefined") return;
      const currentSearchParams = new URLSearchParams(window.location.search);
      const currentQLesson = currentSearchParams.get("lesson");
      const currentHash = window.location.hash || "";
      const currentMatch = currentHash.match(/lesson[-_](\d+)/);
      const currentId = (currentQLesson && /^\d+$/.test(currentQLesson)) ? currentQLesson : (currentMatch ? currentMatch[1] : null);

      if (currentId) {
        fetch(`/api/public/lessons/${currentId}`)
          .then((res) => {
            if (!res.ok) throw new Error(`Lesson #${currentId} not found or server unreachable (${res.status})`);
            return res.json();
          })
          .then((data) => {
            if (active && data && data.title) {
              setPublicLesson(data);
              setLessonError(null);
            } else if (active) {
              setLessonError(`Lesson #${currentId} returned empty content.`);
            }
          })
          .catch((err) => {
            if (active) {
              setLessonError(err.message || "Failed to load lesson.");
            }
          })
          .finally(() => {
            if (active) {
              setInitialLoading(false);
            }
          });
      }
    };

    checkPublicLesson();
    window.addEventListener("hashchange", checkPublicLesson);

    const wantsPreview = searchParams.has("preview") || searchParams.has("demo");

    if (wantsPreview) {
      enableDemoMode();
      setInitialLoading(false);
      return () => {
        active = false;
        clearTimeout(safetyTimer);
        window.removeEventListener("hashchange", checkPublicLesson);
      };
    }

    // If opened directly in browser/Chrome outside Telegram:
    // Don't make the user wait. If a specific lesson was targeted, checkPublicLesson handles it.
    if (!isInsideTelegram() && !getTelegramInitData()) {
      if (targetId) {
        return () => {
          active = false;
          clearTimeout(safetyTimer);
          window.removeEventListener("hashchange", checkPublicLesson);
        };
      }
      // If no specific lesson was targeted, auto-load latest lesson or studio
      fetch("/api/public/lessons")
        .then((res) => (res.ok ? res.json() : []))
        .then((lessons) => {
          if (active && lessons && lessons.length > 0) {
            fetch(`/api/public/lessons/${lessons[0].id}`)
              .then((r) => (r.ok ? r.json() : null))
              .then((data) => {
                if (active && data) {
                  setPublicLesson(data);
                }
              })
              .catch(() => { })
              .finally(() => {
                if (active) setInitialLoading(false);
              });
          } else {
            if (active) setInitialLoading(false);
          }
        })
        .catch(() => {
          if (active) setInitialLoading(false);
        });

      return () => {
        active = false;
        clearTimeout(safetyTimer);
        window.removeEventListener("hashchange", checkPublicLesson);
      };
    }

    try {
      const tg = window.Telegram?.WebApp;
      if (tg) {
        tg.ready?.();
        tg.expand?.();
        if (typeof tg.requestFullscreen === "function") {
          try { tg.requestFullscreen(); } catch (e) { }
        }
        if (typeof tg.disableVerticalSwipes === "function") {
          tg.disableVerticalSwipes();
        }
      }
    } catch (e) { }

    let attempts = 0;
    const attemptAuth = () => {
      if (!active) return;
      const initData = getTelegramInitData();
      if (initData) {
        api("/api/me")
          .then(async (profile) => {
            if (!active) return;
            setAdmin(profile);
            await Promise.all([loadCourses(), loadDashboard(), loadCategories()]);
          })
          .catch((cause) => {
            if (active) setError(cause.message);
          })
          .finally(() => {
            if (active) setInitialLoading(false);
          });
        return;
      }

      attempts++;
      if (attempts < 40) {
        setTimeout(attemptAuth, 100);
      } else {
        if (active) {
          setInitialLoading(false);
          setError("Open this app from the CyberLearn Studio button in your Telegram bot chat, or preview it locally below.");
        }
      }
    };

    attemptAuth();

    return () => {
      active = false;
      clearTimeout(safetyTimer);
      window.removeEventListener("hashchange", checkPublicLesson);
    };
  }, [loadCourses, loadDashboard, loadCategories]);

  useEffect(() => {
    setLesson(null);
    setLessons([]);
    setPreview([]);
    if (courseId) {
      loadLessons(courseId).catch((cause) => setError(cause.message));
      loadQuizzes(courseId).catch((cause) => setError(cause.message));
    } else {
      setQuizzes([]);
    }
  }, [courseId, loadLessons, loadQuizzes]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadLessons(courseId, lessonQuery).catch((cause) =>
        setError(cause.message),
      );
    }, 200);
    return () => window.clearTimeout(timer);
  }, [courseId, lessonQuery, loadLessons]);

  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    if (tg && typeof tg.enableClosingConfirmation === "function") {
      if (hasUnsavedChanges || hasUnsavedQuizChanges) {
        tg.enableClosingConfirmation();
      } else {
        tg.disableClosingConfirmation?.();
      }
    }
    // Only register browser beforeunload if NOT running in Telegram,
    // because Telegram Desktop intercepts HTML beforeunload and minimizes/freezes rather than closing.
    if (!tg?.initData && (!tg?.platform || tg?.platform === "unknown")) {
      if (!hasUnsavedChanges && !hasUnsavedQuizChanges) return undefined;
      const warnBeforeUnload = (event) => {
        event.preventDefault();
        event.returnValue = "";
      };
      window.addEventListener("beforeunload", warnBeforeUnload);
      return () => window.removeEventListener("beforeunload", warnBeforeUnload);
    }
  }, [hasUnsavedChanges, hasUnsavedQuizChanges]);

  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    if (!tg?.BackButton) return undefined;

    const hasSubView = Boolean(lesson || quiz || showTelegramPreview);

    if (hasSubView) {
      tg.BackButton.show();
      const handleBack = () => {
        if (showTelegramPreview) {
          setShowTelegramPreview(false);
        } else if (lesson) {
          setLesson(null);
        } else if (quiz) {
          setQuiz(null);
        }
      };
      tg.BackButton.onClick(handleBack);
      return () => {
        try {
          tg.BackButton.offClick?.(handleBack);
        } catch (e) { }
      };
    } else {
      tg.BackButton.hide();
    }
  }, [lesson, quiz, showTelegramPreview]);

  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    if (!tg?.onEvent) return undefined;
    const updateFs = () => {
      setIsFullscreen(Boolean(tg.isFullscreen));
    };
    tg.onEvent("fullscreenChanged", updateFs);
    return () => {
      try { tg.offEvent?.("fullscreenChanged", updateFs); } catch (e) { }
    };
  }, []);

  useEffect(() => {
    if (!noteImportOpen) return undefined;
    let active = true;
    const timer = window.setTimeout(() => {
      api(`/api/notes?query=${encodeURIComponent(noteQuery)}`)
        .then((data) => active && setBotNotes(data))
        .catch((cause) => active && setError(cause.message));
    }, 200);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [noteImportOpen, noteQuery]);

  useEffect(() => {
    if (!courseMenuOpen) return undefined;
    const handleOutside = (e) => {
      if (courseMenuRef.current && !courseMenuRef.current.contains(e.target)) {
        setCourseMenuOpen(false);
      }
    };
    const handleKey = (e) => {
      if (e.key === "Escape") setCourseMenuOpen(false);
    };
    document.addEventListener("pointerdown", handleOutside);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("pointerdown", handleOutside);
      document.removeEventListener("keydown", handleKey);
    };
  }, [courseMenuOpen]);

  const run = async (action, successMessage = "") => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      if (successMessage) setNotice(successMessage);
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  };

  const confirmLeavingEditor = async () => (
    viewMode === "lessons"
      ? await confirmDiscardChanges()
      : await confirmDiscardQuizChanges()
  );

  const syncHistoryStatus = () => {
    const h = editorHistoryRef.current;
    setHistoryStatus({ canUndo: h.past.length > 0, canRedo: h.future.length > 0 });
  };

  const pushEditorHistory = (prevValue, isTyping = false) => {
    const h = editorHistoryRef.current;
    const now = Date.now();
    if (isTyping && h.past.length > 0 && now - h.lastTypedAt < 800) {
      h.lastTypedAt = now;
      return;
    }
    if (h.past[h.past.length - 1] !== prevValue) {
      h.past.push(prevValue);
      if (h.past.length > 60) h.past.shift();
    }
    h.future = [];
    h.lastTypedAt = isTyping ? now : 0;
    syncHistoryStatus();
  };

  const applyEditorSnapshot = (value) => {
    const textarea = contentRef.current;
    setContent(value);
    if (textarea) {
      textarea.value = value;
      textarea.focus();
    }
  };

  const handleUndo = () => {
    const h = editorHistoryRef.current;
    if (!h.past.length) return;
    const current = contentRef.current ? contentRef.current.value : content;
    const previous = h.past.pop();
    h.future.push(current);
    applyEditorSnapshot(previous);
    syncHistoryStatus();
  };

  const handleRedo = () => {
    const h = editorHistoryRef.current;
    if (!h.future.length) return;
    const current = contentRef.current ? contentRef.current.value : content;
    const next = h.future.pop();
    h.past.push(current);
    applyEditorSnapshot(next);
    syncHistoryStatus();
  };

  const updateEditorContent = (newValue, newStart, newEnd) => {
    const textarea = contentRef.current;
    const prevValue = textarea ? textarea.value : content;
    if (prevValue !== newValue) {
      pushEditorHistory(prevValue, false);
    }
    setContent(newValue);
    if (textarea) {
      textarea.value = newValue;
      textarea.setSelectionRange(newStart, newEnd);
      textarea.focus();
      requestAnimationFrame(() => {
        if (contentRef.current) {
          contentRef.current.setSelectionRange(newStart, newEnd);
        }
      });
    }
    const active = detectActiveFormat(newValue, newStart, newEnd);
    setFormattingActive(active);
  };

  const handleEditorSelectionChange = () => {
    const textarea = contentRef.current;
    if (!textarea) return;
    const active = detectActiveFormat(textarea.value, textarea.selectionStart, textarea.selectionEnd);
    setFormattingActive(active);
  };

  const applyFormat = (format) => {
    const textarea = contentRef.current;
    const val = textarea ? textarea.value : content;
    const start = textarea ? textarea.selectionStart : 0;
    const end = textarea ? textarea.selectionEnd : 0;

    switch (format) {
      case "bold": {
        const res = applyInlineFormat(val, start, end, "**");
        updateEditorContent(res.value, res.selectionStart, res.selectionEnd);
        break;
      }
      case "italic": {
        const res = applyInlineFormat(val, start, end, "*");
        updateEditorContent(res.value, res.selectionStart, res.selectionEnd);
        break;
      }
      case "heading": {
        const res = applyLinePrefix(val, start, end, "## ", /^#{1,6}\s+/);
        updateEditorContent(res.value, res.selectionStart, res.selectionEnd);
        break;
      }
      case "bullet": {
        const res = applyLinePrefix(val, start, end, "- ", /^\s*[-*]\s+/);
        updateEditorContent(res.value, res.selectionStart, res.selectionEnd);
        break;
      }
      case "numbered": {
        const res = applyNumberedList(val, start, end);
        updateEditorContent(res.value, res.selectionStart, res.selectionEnd);
        break;
      }
      case "quote": {
        const res = applyLinePrefix(val, start, end, "> ", /^\s*>\s+/);
        updateEditorContent(res.value, res.selectionStart, res.selectionEnd);
        break;
      }
      case "inline-code": {
        const res = applyInlineFormat(val, start, end, "`");
        updateEditorContent(res.value, res.selectionStart, res.selectionEnd);
        break;
      }
      case "code": {
        const res = applyCodeBlock(val, start, end);
        updateEditorContent(res.value, res.selectionStart, res.selectionEnd);
        break;
      }
      case "link": {
        if (linkDialog?.isOpen) {
          setLinkDialog(null);
          return;
        }
        const selected = val.substring(start, end);
        setLinkDialog({
          isOpen: true,
          start,
          end,
          text: selected,
          url: "https://",
        });
        break;
      }
      default:
        break;
    }
  };

  const handleEditorKeyDown = (event) => {
    const textarea = contentRef.current;
    if (!textarea) return;

    const isMod = event.ctrlKey || event.metaKey;

    if (isMod && !event.shiftKey && !event.altKey) {
      if (event.key === "b" || event.key === "B") {
        event.preventDefault();
        applyFormat("bold");
        return;
      }
      if (event.key === "i" || event.key === "I") {
        event.preventDefault();
        applyFormat("italic");
        return;
      }
      if (event.key === "k" || event.key === "K") {
        event.preventDefault();
        applyFormat("link");
        return;
      }
      if (event.key === "e" || event.key === "E") {
        event.preventDefault();
        applyFormat("inline-code");
        return;
      }
      if (event.key === "z" || event.key === "Z") {
        event.preventDefault();
        handleUndo();
        return;
      }
      if (event.key === "y" || event.key === "Y") {
        event.preventDefault();
        handleRedo();
        return;
      }
    }

    if (isMod && event.shiftKey && !event.altKey && (event.key === "z" || event.key === "Z")) {
      event.preventDefault();
      handleRedo();
      return;
    }

    if (event.key === "Tab") {
      event.preventDefault();
      const res = handleTab(textarea.value, textarea.selectionStart, textarea.selectionEnd, event.shiftKey);
      updateEditorContent(res.value, res.selectionStart, res.selectionEnd);
      return;
    }

    if (event.key === "Enter" && !event.shiftKey && !event.ctrlKey && !event.metaKey && !event.altKey) {
      const res = handleSmartEnter(textarea.value, textarea.selectionStart);
      if (res) {
        event.preventDefault();
        updateEditorContent(res.value, res.selectionStart, res.selectionEnd);
      }
    }
  };

  const createCourse = async (event) => {
    event.preventDefault();
    if (!await confirmLeavingEditor()) return;
    run(async () => {
      const created = await api("/api/courses", {
        method: "POST",
        body: JSON.stringify(courseForm),
      });
      setCourseForm(EMPTY_COURSE);
      setShowNewCourseForm(false);
      await loadCourses();
      setCourseId(String(created.id));
      setLesson(null);
      setQuiz(null);
      setLessonQuery("");
      await loadDashboard();
    }, "Course created.");
  };

  const createLesson = async () => {
    if (!courseId || selectedCourse?.is_archived) return;
    if (!await confirmLeavingEditor()) return;
    run(async () => {
      const created = await api(`/api/courses/${courseId}/lessons`, {
        method: "POST",
        body: JSON.stringify({ title: "Untitled lesson", source_content: "" }),
      });
      await loadLessons(courseId);
      await loadLesson(created.id);
      setLessonQuery("");
      await loadDashboard();
    }, "Draft created.");
  };

  const importBotNote = async (noteId) => {
    if (!await confirmLeavingEditor()) return;
    return run(async () => {
      const imported = await api(`/api/courses/${courseId}/notes/${noteId}/import`, {
        method: "POST",
      });
      await loadLessons(courseId);
      await loadLesson(imported.id);
      setNoteImportOpen(false);
      setNoteQuery("");
      setLessonQuery("");
      await loadDashboard();
    }, "Bot note imported as a lesson draft. The original note remains unchanged.");
  };

  const saveLesson = async () => {
    if (!lesson) return;
    const lessonContent = content.trim() ? content : sourceContent;
    if (lessonContent !== content) setContent(lessonContent);
    const saved = await api(`/api/lessons/${lesson.id}`, {
      method: "PUT",
      body: JSON.stringify({
        title: lessonTitle,
        source_content: sourceContent,
        content: lessonContent,
      }),
    });
    setLesson(saved);
    if (saved.title && saved.title !== lessonTitle) {
      setLessonTitle(saved.title);
    }
    if (saved.content && saved.content !== content) {
      setContent(saved.content);
    }
    setLastSavedTime(Date.now());
    await loadLessons(courseId, lessonQuery);
    await loadDashboard();
    return saved;
  };

  const deleteLesson = async (targetLessonId) => {
    const idToDelete = targetLessonId || lesson?.id;
    if (!idToDelete) return;
    const lessonObj = lessons.find((l) => l.id === idToDelete) || lesson;
    const title = lessonObj?.title || `Lesson #${idToDelete}`;
    const confirmed = await confirmAction({
      title: "Delete Lesson?",
      message: `Are you sure you want to delete "${title}"? This cannot be undone.`,
      confirmText: "Delete",
      cancelText: "Cancel",
      danger: true,
    });
    if (!confirmed) return;
    run(async () => {
      await api(`/api/lessons/${idToDelete}`, { method: "DELETE" });
      if (lesson && lesson.id === idToDelete) {
        setLesson(null);
        setLessonTitle("");
        setSourceContent("");
        setContent("");
      }
      await loadLessons(courseId, lessonQuery);
      await loadDashboard();
    }, `Lesson "${title}" deleted.`);
  };

  const deleteQuiz = async (targetQuizId) => {
    const idToDelete = targetQuizId || quiz?.id;
    if (!idToDelete) return;
    const quizObj = quizzes.find((q) => q.id === idToDelete) || quiz;
    const title = quizObj?.title || `Quiz #${idToDelete}`;
    const confirmed = await confirmAction({
      title: "Delete Quiz?",
      message: `Are you sure you want to delete "${title}"? This cannot be undone.`,
      confirmText: "Delete",
      cancelText: "Cancel",
      danger: true,
    });
    if (!confirmed) return;
    run(async () => {
      await api(`/api/quizzes/${idToDelete}`, { method: "DELETE" });
      if (quiz && quiz.id === idToDelete) {
        setQuiz(null);
        setQuizTitle("");
        setQuizInstructions("");
        setQuizQuestions([]);
      }
      await loadQuizzes(courseId);
      await loadDashboard();
    }, `Quiz "${title}" deleted.`);
  };

  const createQuiz = async () => {
    if (!courseId || selectedCourse?.is_archived) return;
    if (!await confirmLeavingEditor()) return;
    run(async () => {
      const created = await api(`/api/courses/${courseId}/quizzes`, {
        method: "POST",
      });
      await loadQuizzes(courseId);
      setViewMode("quizzes");
      await loadQuiz(created.id);
      await loadDashboard();
    }, "Quiz draft created.");
  };

  const validateQuizBeforeSave = () => {
    if (!quizTitle.trim()) {
      return "Quiz title cannot be blank.";
    }
    for (let i = 0; i < quizQuestions.length; i++) {
      const q = quizQuestions[i];
      const qNum = i + 1;
      if (!q.question_text.trim()) {
        return `Question ${qNum}: Question text cannot be blank.`;
      }
      if (q.question_type === "true_false") {
        if (q.options.length !== 2) {
          return `Question ${qNum} (True/False): Must have exactly 2 options (True and False).`;
        }
        const correctCount = q.options.filter((opt) => opt.is_correct).length;
        if (correctCount !== 1) {
          return `Question ${qNum} (True/False): Please select whether True or False is the correct answer.`;
        }
      } else if (q.question_type === "multiple_choice") {
        if (q.options.length < 2 || q.options.length > 10) {
          return `Question ${qNum} (Multiple Choice): Must have between 2 and 10 answer options.`;
        }
        for (let j = 0; j < q.options.length; j++) {
          const letter = String.fromCharCode(65 + j);
          if (!q.options[j].option_text.trim()) {
            return `Question ${qNum}, Option ${letter}: Option text cannot be blank.`;
          }
        }
        const correctCount = q.options.filter((opt) => opt.is_correct).length;
        if (correctCount !== 1) {
          return `Question ${qNum} (Multiple Choice): Please select exactly one correct answer.`;
        }
      } else {
        return `Question ${qNum}: Unsupported format "${q.question_type}". Only Multiple Choice and True/False are supported.`;
      }
    }
    return null;
  };

  const saveQuiz = async () => {
    if (!quiz) return;
    const validationError = validateQuizBeforeSave();
    if (validationError) {
      setError(validationError);
      throw new Error(validationError);
    }
    const saved = await api(`/api/quizzes/${quiz.id}`, {
      method: "PUT",
      body: JSON.stringify({
        title: quizTitle,
        instructions: quizInstructions,
        difficulty: quizDifficulty,
        duration_minutes: quizDuration ? Number(quizDuration) : null,
        questions: quizQuestions.map((question) => ({
          question_type: question.question_type,
          question_text: question.question_text,
          explanation: question.explanation,
          difficulty: question.difficulty,
          options: question.options.map((option) => ({
            option_text: option.option_text,
            match_text: null,
            is_correct: option.is_correct,
          })),
        })),
      }),
    });
    await loadQuiz(saved.id);
    setLastSavedTime(Date.now());
    await loadQuizzes(courseId);
    await loadDashboard();
  };

  // Keyboard shortcut Ctrl/Cmd+S to save draft (placed after saveLesson and saveQuiz initialization)
  useEffect(() => {
    const handleKeyDown = (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        if (viewMode === "lessons" && lesson) {
          event.preventDefault();
          run(saveLesson, "Draft saved.");
        } else if (viewMode === "quizzes" && quiz) {
          event.preventDefault();
          run(saveQuiz, "Quiz draft saved.");
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [viewMode, lesson, quiz, saveLesson, saveQuiz]);

  const approveQuiz = () => run(async () => {
    if (!quiz) return;
    const validationError = validateQuizBeforeSave();
    if (validationError) {
      setError(validationError);
      throw new Error(validationError);
    }
    await saveQuiz();
    await api(`/api/quizzes/${quiz.id}/approve`, { method: "POST" });
    await loadQuiz(quiz.id);
    await loadQuizzes(courseId);
  }, "This quiz version is approved and ready to publish.");

  const publishQuiz = () => run(async () => {
    if (!quiz) return;
    await api(`/api/quizzes/${quiz.id}/publish`, { method: "POST" });
    await loadQuiz(quiz.id);
    await loadQuizzes(courseId);
    await loadDashboard();
  }, "Interactive quiz polls published to your linked Telegram channel.");

  const addQuizQuestion = (questionType = newQuestionType) => {
    const effectiveType = QUESTION_TYPES.some(([value]) => value === questionType)
      ? questionType
      : "multiple_choice";
    let options;
    if (effectiveType === "true_false") {
      options = [
        { option_text: "True", match_text: null, is_correct: false },
        { option_text: "False", match_text: null, is_correct: false },
      ];
    } else {
      options = [
        { option_text: "", match_text: null, is_correct: false },
        { option_text: "", match_text: null, is_correct: false },
        { option_text: "", match_text: null, is_correct: false },
        { option_text: "", match_text: null, is_correct: false },
      ];
    }
    setQuizQuestions((current) => [
      ...current,
      {
        question_type: effectiveType,
        question_text: "",
        explanation: "",
        difficulty: "medium",
        options,
      },
    ]);
  };

  const updateQuizQuestion = (questionIndex, update) => {
    setQuizQuestions((current) =>
      current.map((question, index) =>
        index === questionIndex ? { ...question, ...update } : question,
      ),
    );
  };

  const changeQuestionType = (questionIndex, questionType) => {
    const question = quizQuestions[questionIndex];
    if (!question || !QUESTION_TYPES.some(([val]) => val === questionType)) return;
    let options;
    if (questionType === "true_false") {
      options = [
        { option_text: "True", match_text: null, is_correct: false },
        { option_text: "False", match_text: null, is_correct: false },
      ];
    } else {
      const preserved = question.options
        .filter((opt) => opt.option_text && !["true", "false"].includes(opt.option_text.toLowerCase()))
        .slice(0, 10);
      options = [
        { option_text: preserved[0]?.option_text ?? "", match_text: null, is_correct: false },
        { option_text: preserved[1]?.option_text ?? "", match_text: null, is_correct: false },
        { option_text: preserved[2]?.option_text ?? "", match_text: null, is_correct: false },
        { option_text: preserved[3]?.option_text ?? "", match_text: null, is_correct: false },
      ];
    }
    updateQuizQuestion(questionIndex, {
      question_type: questionType,
      options,
    });
  };

  const updateQuizOption = (questionIndex, optionIndex, update) => {
    setQuizQuestions((current) =>
      current.map((question, index) => {
        if (index !== questionIndex) return question;
        return {
          ...question,
          options: question.options.map((option, currentOptionIndex) => {
            if (currentOptionIndex === optionIndex) {
              return { ...option, ...update };
            }
            if (update.is_correct) {
              return { ...option, is_correct: false };
            }
            return option;
          }),
        };
      }),
    );
  };

  const moveQuizQuestion = (questionIndex, direction) => {
    setQuizQuestions((current) => {
      const targetIndex = questionIndex + direction;
      if (targetIndex < 0 || targetIndex >= current.length) return current;
      const reordered = [...current];
      [reordered[questionIndex], reordered[targetIndex]] = [
        reordered[targetIndex],
        reordered[questionIndex],
      ];
      return reordered;
    });
  };

  const moveQuizOption = (questionIndex, optionIndex, direction) => {
    setQuizQuestions((current) =>
      current.map((question, index) => {
        if (index !== questionIndex) return question;
        const targetIndex = optionIndex + direction;
        if (targetIndex < 0 || targetIndex >= question.options.length) return question;
        const options = [...question.options];
        [options[optionIndex], options[targetIndex]] = [
          options[targetIndex],
          options[optionIndex],
        ];
        return { ...question, options };
      }),
    );
  };

  const selectQuiz = async (quizId) => {
    if (!await confirmLeavingEditor()) return;
    run(async () => {
      setViewMode("quizzes");
      await loadQuiz(quizId);
    });
  };

  const changeViewMode = (nextMode) => {
    if (nextMode === viewMode) return;
    setViewMode(nextMode);
    setNoteImportOpen(false);
  };

  useEffect(() => {
    try {
      const activeBtn = document.querySelector(".header-nav button.active");
      if (activeBtn && typeof activeBtn.scrollIntoView === "function") {
        activeBtn.scrollIntoView({ behavior: "smooth", inline: "nearest", block: "nearest" });
      }
    } catch (e) { }
  }, [viewMode]);

  const saveCourse = (event) => {
    event.preventDefault();
    if (!selectedCourse) return;
    run(async () => {
      await api(`/api/courses/${selectedCourse.id}`, {
        method: "PUT",
        body: JSON.stringify(courseEditForm),
      });
      await loadCourses();
      await loadDashboard();
      setEditingCourse(false);
    }, "Course details saved.");
  };

  const toggleCourseArchive = async () => {
    if (!selectedCourse) return;
    const action = selectedCourse.is_archived ? "restore" : "archive";
    const confirmed = await confirmAction({
      title: `${action === "archive" ? "Archive" : "Restore"} Course?`,
      message: `Are you sure you want to ${action} "${selectedCourse.title}"?`,
      confirmText: action === "archive" ? "Archive Course" : "Restore Course",
      cancelText: "Cancel",
      danger: action === "archive",
    });
    if (!confirmed) return;
    run(async () => {
      await api(`/api/courses/${selectedCourse.id}/archive`, {
        method: "PATCH",
        body: JSON.stringify({ is_archived: !selectedCourse.is_archived }),
      });
      await loadCourses();
      await loadDashboard();
      if (!selectedCourse.is_archived) setShowArchivedCourses(true);
    }, `Course ${selectedCourse.is_archived ? "restored" : "archived"}.`);
  };

  const selectCourse = async (nextCourseId) => {
    if (nextCourseId === courseId) return;
    if (!await confirmLeavingEditor()) return;
    setCourseId(nextCourseId);
    setLesson(null);
    setQuiz(null);
    setLessonQuery("");
    setEditingCourse(false);
  };

  const previewLesson = () => {
    if (showTelegramPreview) {
      setShowTelegramPreview(false);
      return;
    }
    const lessonContent = content.trim() ? content : sourceContent;
    if (!lessonContent.trim()) {
      setError("Add lesson text or source material before previewing.");
      return;
    }
    if (lessonContent !== content) setContent(lessonContent);
    setShowTelegramPreview(true);
    if (lesson?.id) {
      api(`/api/lessons/${lesson.id}/preview`, {
        method: "POST",
        body: JSON.stringify({ title: lessonTitle, content: lessonContent }),
      })
        .then((result) => setPreview(result?.parts || []))
        .catch(() => { });
    }
  };

  const approveLesson = () => run(async () => {
    if (!lesson) return;
    await saveLesson();
    await api(`/api/lessons/${lesson.id}/approve`, { method: "POST" });
    await loadLesson(lesson.id);
    await loadLessons(courseId);
    await loadDashboard();
  }, "This version is approved. Publish it when you are ready.");

  const publishLesson = (mode = "card") => run(async () => {
    if (!lesson) return;
    await api(`/api/lessons/${lesson.id}/publish?mode=${mode}`, { method: "POST" });
    await loadLesson(lesson.id);
    await loadLessons(courseId);
    await loadDashboard();
  }, mode === "card" ? "Published announcement card with reader button to channel." : "Published full text chunks to channel.");

  const retryPublish = (mode = "card") => run(async () => {
    if (!lesson) return;
    await api(`/api/lessons/${lesson.id}/publish?mode=${mode}`, { method: "POST" });
    await loadLesson(lesson.id);
    await loadLessons(courseId);
    await loadDashboard();
  }, "Publish retry completed.");

  const enableDemoMode = () => {
    setError("");
    setAdmin({ id: 1069798010, first_name: "Teacher", username: "admin" });
    const demoCourses = [
      { id: 1, title: "Introduction to Cybersecurity", lesson_count: 2, is_archived: false, description: "Core concepts of information security and system hardening." },
      { id: 2, title: "Network Defense & Analysis", lesson_count: 1, is_archived: false, description: "Packet inspection, ports, and firewall configuration." },
    ];
    setCourses(demoCourses);
    setCourseId("1");
    setCategories([
      { id: 1, name: "Fundamentals", color: "#4f46e5", course_count: 1 },
      { id: 2, name: "Networking", color: "#059669", course_count: 1 },
    ]);
    setDashboard({
      course_count: 2,
      lesson_count: 3,
      quiz_count: 1,
      draft_count: 1,
      ready_count: 1,
      published_count: 1,
      failed_publish_count: 0,
      recent_activity: [
        {
          job_id: 1,
          lesson_title: "The CIA Triad",
          course_title: "Introduction to Cybersecurity",
          channel_id: "@cyberlearn_channel",
          status: "published",
          telegram_message_ids: [102],
          updated_at: new Date().toISOString(),
        },
      ],
    });
    const demoLessons = [
      {
        id: 101,
        course_id: 1,
        course_title: "Introduction to Cybersecurity",
        title: "The CIA Triad",
        status: "published",
        updated_at: new Date().toISOString(),
        source_content: "Confidentiality ensures only authorized users access data. Integrity ensures data isn't modified. Availability ensures systems are online when needed.",
        content: "## The CIA Triad\n\nThe foundation of information security rests upon three core pillars:\n\n- **Confidentiality**: Protection from unauthorized observation or disclosure.\n- **Integrity**: Assurance that data remains unaltered and trustworthy.\n- **Availability**: Guarantee that services remain reachable for legitimate users.\n\n> In educational environments, balance usability with defense-in-depth principles.",
      },
      {
        id: 102,
        course_id: 1,
        course_title: "Introduction to Cybersecurity",
        title: "Threat Modeling Essentials",
        status: "draft",
        updated_at: new Date().toISOString(),
        source_content: "Threat modeling identifies what can go wrong in a system before deployment.",
        content: "## Threat Modeling\n\nIdentify potential adversaries, attack surfaces, and mitigations early in your architecture design.",
      },
    ];
    setLessons(demoLessons);
    setLesson(demoLessons[0]);
    setLessonTitle(demoLessons[0].title);
    setSourceContent(demoLessons[0].source_content);
    setContent(demoLessons[0].content);
    const demoQuizzes = [
      {
        id: 1,
        course_id: 1,
        title: "Security Principles Knowledge Check",
        difficulty: "easy",
        instructions: "Test your understanding of the CIA triad and basic security terminology.",
        duration_minutes: 10,
        questions: [
          {
            id: 1,
            question_type: "multiple_choice",
            question_text: "Which pillar of the CIA triad ensures that data has not been tampered with or modified?",
            difficulty: "easy",
            explanation: "Integrity guarantees that information is authentic and free from unauthorized alteration.",
            options: [
              { option_text: "Confidentiality", is_correct: false },
              { option_text: "Integrity", is_correct: true },
              { option_text: "Availability", is_correct: false },
              { option_text: "Non-repudiation", is_correct: false },
            ],
          },
        ],
        latest_version: {
          id: 1,
          version_number: 1,
          status: "approved",
          snapshot: {
            title: "Security Principles Knowledge Check",
            difficulty: "easy",
            instructions: "Test your understanding of the CIA triad and basic security terminology.",
            duration_minutes: 10,
            questions: [
              {
                question_type: "multiple_choice",
                question_text: "Which pillar of the CIA triad ensures that data has not been tampered with or modified?",
                difficulty: "easy",
                explanation: "Integrity guarantees that information is authentic and free from unauthorized alteration.",
                options: [
                  { option_text: "Confidentiality", is_correct: false },
                  { option_text: "Integrity", is_correct: true },
                  { option_text: "Availability", is_correct: false },
                  { option_text: "Non-repudiation", is_correct: false },
                ],
              },
            ],
          },
        },
      },
    ];
    setQuizzes(demoQuizzes);
    setQuiz(demoQuizzes[0]);
    setQuizTitle(demoQuizzes[0].title);
    setQuizInstructions(demoQuizzes[0].instructions);
    setQuizDifficulty(demoQuizzes[0].difficulty);
    setQuizDuration("10");
    setQuizQuestions(demoQuizzes[0].questions);
    setInitialLoading(false);
  };

  if (initialLoading) {
    return (
      <main className="auth-screen">
        <div className="auth-card" style={{ textAlign: "center" }}>
          <div className="brand-mark" style={{ margin: "0 auto var(--space-4)" }}>C</div>
          <p className="eyebrow accent">CYBERLEARN STUDIO</p>
          <h2 style={{ margin: "var(--space-2) 0 var(--space-3)", font: "600 20px var(--font-display)", color: "var(--text)" }}>
            Loading workspace…
          </h2>
          <p className="muted small" style={{ margin: "0 0 var(--space-4)" }}>
            Connecting to study notes service...
          </p>
          <button
            type="button"
            className="ghost-button"
            style={{ margin: "0 auto", fontSize: "12px" }}
            onClick={() => setInitialLoading(false)}
          >
            Skip wait →
          </button>
        </div>
      </main>
    );
  }

  if (lessonError && !publicLesson) {
    return (
      <main className="auth-screen">
        <div className="auth-card" style={{ textAlign: "center" }}>
          <div className="brand-mark" style={{ margin: "0 auto var(--space-4)" }}>📖</div>
          <p className="eyebrow accent">ACADEMIC COURSEWARE</p>
          <h2 style={{ margin: "var(--space-2) 0 var(--space-3)", font: "600 20px var(--font-display)", color: "var(--text)" }}>
            Unable to load lesson
          </h2>
          <div className="error-box" style={{ marginBottom: "var(--space-4)" }}>
            {lessonError}
          </div>
          <p className="muted small" style={{ marginBottom: "var(--space-4)" }}>
            If the link was posted recently, the study tunnel may be reconnecting. You can retry or open the reader preview.
          </p>
          <div style={{ display: "flex", gap: "var(--space-2)", justifyContent: "center", flexWrap: "wrap" }}>
            <button
              type="button"
              className="publish-button"
              onClick={() => window.location.reload()}
            >
              ↻ Retry Connection
            </button>
          </div>
        </div>
      </main>
    );
  }

  if (publicLesson) {
    const inTgPublic = isInsideTelegram();
    return (
      <main
        className={`app-shell app-shell-public ${inTgPublic ? "in-telegram" : ""}`}
        data-in-telegram={inTgPublic ? "true" : "false"}
        style={{ height: "100dvh", overflow: "hidden", padding: 0 }}
      >
        <TelegramPreview
          courseTitle={publicLesson.course_title || "Course"}
          lessonTitle={publicLesson.title || "Lesson"}
          content={publicLesson.content || ""}
          publicMode={true}
          onClose={() => {
            setPublicLesson(null);
            if (typeof window !== "undefined") {
              window.location.hash = "";
            }
          }}
          onOpenStudio={
            admin
              ? () => {
                  setPublicLesson(null);
                  if (typeof window !== "undefined") {
                    window.location.hash = "";
                  }
                }
              : null
          }
        />
      </main>
    );
  }

  if (!admin) {
    return <AuthScreen error={error} />;
  }

  const isFullWidthView = ["courses", "calendar", "publishing", "settings"].includes(viewMode);
  const inTelegram = isInsideTelegram();

  const insertImageMarkdownAtCursor = (imageUrl) => {
    const textarea = contentRef.current;
    const currentVal = textarea ? textarea.value : content;
    const start = textarea ? textarea.selectionStart : currentVal.length;
    const end = textarea ? textarea.selectionEnd : currentVal.length;
    const prefix = start > 0 && currentVal[start - 1] !== "\n" ? "\n\n" : "";
    const suffix = end < currentVal.length && currentVal[end] !== "\n" ? "\n\n" : "\n";
    const snippet = `${prefix}![Explanation image](${imageUrl})${suffix}`;
    const nextVal = currentVal.slice(0, start) + snippet + currentVal.slice(end);
    const nextCursor = start + snippet.length;
    updateEditorContent(nextVal, nextCursor, nextCursor);
  };

  const encodeImageForUpload = async (file) => {
    const readAsDataUrl = (blob) =>
      new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ""));
        reader.onerror = () => reject(new Error("Could not read image file."));
        reader.readAsDataURL(blob);
      });

    const rawDataUrl = await readAsDataUrl(file);
    const mime = (file.type || "").toLowerCase();
    const supportedDirect = new Set(["image/png", "image/jpeg", "image/webp", "image/gif"]);
    // Keep small standard images or animated GIFs as-is
    if ((mime === "image/gif" || (supportedDirect.has(mime) && file.size <= 350_000))) {
      return { mimeType: mime, dataBase64: rawDataUrl };
    }

    // Resize/compress or convert non-standard formats (heic, bmp, avif, empty mime) via canvas
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => {
        const maxWidth = 1400;
        let { width, height } = img;
        if (width > maxWidth) {
          height = Math.round((height * maxWidth) / width);
          width = maxWidth;
        }
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          resolve({ mimeType: supportedDirect.has(mime) ? mime : "image/png", dataBase64: rawDataUrl });
          return;
        }
        ctx.drawImage(img, 0, 0, width, height);
        const targetMime = mime === "image/png" ? "image/png" : "image/jpeg";
        const compressed = canvas.toDataURL(targetMime, 0.85);
        resolve({ mimeType: targetMime, dataBase64: compressed });
      };
      img.onerror = () => resolve({ mimeType: supportedDirect.has(mime) ? mime : "image/png", dataBase64: rawDataUrl });
      img.src = rawDataUrl;
    });
  };

  const restoreTelegramWindowSize = () => {
    try {
      const tg = window.Telegram?.WebApp;
      if (!tg) return;
      const runRestore = () => {
        try {
          tg.expand?.();
          if (wantsFullscreenRef.current && typeof tg.requestFullscreen === "function" && !tg.isFullscreen) {
            tg.requestFullscreen();
          }
        } catch {}
      };
      runRestore();
      setTimeout(runRestore, 180);
      setTimeout(runRestore, 500);
    } catch {}
  };

  const handleUploadLessonImage = async (file) => {
    if (!file) return;
    restoreTelegramWindowSize();
    setImageUploading(true);
    setError("");
    try {
      const { mimeType, dataBase64 } = await encodeImageForUpload(file);
      const uploaded = await api("/api/images", {
        method: "POST",
        timeoutMs: 30000,
        body: JSON.stringify({
          lesson_id: lesson?.id ?? null,
          file_name: file.name || "pasted-image.png",
          mime_type: mimeType,
          data_base64: dataBase64,
        }),
      });
      insertImageMarkdownAtCursor(uploaded.url);
      setNotice("Image added to lesson!");
    } catch (err) {
      setError(err.message || "Failed to upload image.");
    } finally {
      setImageUploading(false);
    }
  };

  const handlePasteImageFromClipboard = async () => {
    setError("");
    try {
      if (navigator.clipboard?.read) {
        const items = await navigator.clipboard.read();
        for (const item of items) {
          const imgType = item.types.find((t) => t.startsWith("image/"));
          if (imgType) {
            const blob = await item.getType(imgType);
            const file = new File([blob], "pasted-image.png", { type: imgType });
            await handleUploadLessonImage(file);
            return;
          }
          if (item.types.includes("text/html")) {
            const htmlBlob = await item.getType("text/html");
            const htmlText = await htmlBlob.text();
            const dataUriMatch = htmlText.match(/<img[^>]+src=["'](data:image\/[^"']+)["']/i);
            if (dataUriMatch) {
              const res = await fetch(dataUriMatch[1]);
              const blob = await res.blob();
              await handleUploadLessonImage(new File([blob], "pasted-image.png", { type: blob.type || "image/png" }));
              return;
            }
            const remoteImgMatch = htmlText.match(/<img[^>]+src=["'](https?:\/\/[^"']+)["']/i);
            if (remoteImgMatch) {
              await handleImportImageUrl(remoteImgMatch[1]);
              return;
            }
          }
        }
      }
      if (navigator.clipboard?.readText) {
        const txt = (await navigator.clipboard.readText()).trim();
        if (/^https?:\/\/\S+\.(?:png|jpe?g|webp|gif)(?:\?\S*)?$/i.test(txt)) {
          await handleImportImageUrl(txt);
          return;
        }
      }
      setError("No image found in clipboard. Try copying an image or use the Image button.");
    } catch (err) {
      setError("Clipboard access was blocked by the browser. Use Ctrl+V inside the text box or tap Image.");
    }
  };

  const handleImportImageUrl = async (url) => {
    setImageUploading(true);
    setError("");
    try {
      const uploaded = await api("/api/images/from-url", {
        method: "POST",
        timeoutMs: 25000,
        body: JSON.stringify({
          lesson_id: lesson?.id ?? null,
          url,
        }),
      });
      insertImageMarkdownAtCursor(uploaded.url);
      setNotice("Image copied and saved to lesson!");
    } catch {
      // Fallback to direct markdown image link if remote host blocks server fetch
      insertImageMarkdownAtCursor(url);
      setNotice("Image link added to lesson!");
    } finally {
      setImageUploading(false);
    }
  };

  const handleEditorPaste = async (event) => {
    const clipboard = event.clipboardData;
    if (!clipboard) return;

    // 1. Direct image items/files in clipboard (screenshots, Copy Image from browser, etc.)
    const items = Array.from(clipboard.items || []);
    const imageItem = items.find((item) => item.kind === "file" && item.type.startsWith("image/"));
    if (imageItem) {
      const file = imageItem.getAsFile();
      if (file) {
        event.preventDefault();
        await handleUploadLessonImage(file);
        return;
      }
    }

    const files = Array.from(clipboard.files || []);
    const imageFile = files.find((f) => f.type.startsWith("image/") || /\.(png|jpe?g|webp|gif|bmp|heic)$/i.test(f.name || ""));
    if (imageFile) {
      event.preventDefault();
      await handleUploadLessonImage(imageFile);
      return;
    }

    // 2. Pasted HTML containing <img src="data:image/..."> or <img src="https://...">
    const htmlData = clipboard.getData("text/html");
    if (htmlData) {
      const dataUriMatch = htmlData.match(/<img[^>]+src=["'](data:image\/[^"']+)["']/i);
      if (dataUriMatch) {
        event.preventDefault();
        try {
          const res = await fetch(dataUriMatch[1]);
          const blob = await res.blob();
          const pastedFile = new File([blob], "pasted-image.png", { type: blob.type || "image/png" });
          await handleUploadLessonImage(pastedFile);
        } catch {
          setError("Could not read pasted image from clipboard.");
        }
        return;
      }

      const remoteImgMatch = htmlData.match(/<img[^>]+src=["'](https?:\/\/[^"']+)["']/i);
      if (remoteImgMatch && !clipboard.getData("text/plain")?.trim()) {
        event.preventDefault();
        await handleImportImageUrl(remoteImgMatch[1]);
        return;
      }
    }

    // 3. Plain-text direct image URL (e.g. Copy Image Address)
    const plainText = (clipboard.getData("text/plain") || "").trim();
    if (/^https?:\/\/\S+\.(?:png|jpe?g|webp|gif)(?:\?\S*)?$/i.test(plainText)) {
      event.preventDefault();
      await handleImportImageUrl(plainText);
    }
  };

  const handleToggleFullscreen = () => {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;
    try {
      if (tg.isFullscreen) {
        wantsFullscreenRef.current = false;
        if (typeof tg.exitFullscreen === "function") {
          tg.exitFullscreen();
        }
      } else {
        wantsFullscreenRef.current = true;
        if (typeof tg.requestFullscreen === "function") {
          tg.requestFullscreen();
        }
      }
    } catch (e) { }
  };

  const handleExitStudio = (e) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    try {
      const tg = window.Telegram?.WebApp;
      if (tg) {
        if (typeof tg.disableClosingConfirmation === "function") {
          try {
            tg.disableClosingConfirmation();
          } catch (err) { }
        }
        if (typeof tg.close === "function") {
          tg.close();
          return;
        }
      }
    } catch (err) {
      console.error("Failed to close Telegram WebApp:", err);
    }
    try {
      window.close();
    } catch (err) { }
  };

  return (
    <main
      className={`app-shell ${inTelegram ? "in-telegram" : ""}`}
      data-in-telegram={inTelegram ? "true" : "false"}
      data-is-fullscreen={isFullscreen ? "true" : "false"}
    >
      <header className={`topbar ${inTelegram ? "in-telegram" : ""}`}>
        <div className="topbar-main-row">
          <div className="brand">
            <div className="brand-mark">C</div>
            <div className="brand-text">
              <strong>CyberLearn</strong>
              <span className="brand-badge">Studio</span>
            </div>
          </div>
          <div className="topbar-right">
            {admin && <span className="admin-name">{admin.first_name || admin.username}</span>}
            {inTelegram && typeof window !== "undefined" && Boolean(window.Telegram?.WebApp?.requestFullscreen) && (
              <button
                type="button"
                className="fullscreen-toggle-btn"
                onClick={handleToggleFullscreen}
                title={isFullscreen ? "Exit full window" : "Expand to full window"}
                aria-label={isFullscreen ? "Exit full window" : "Expand to full window"}
              >
                <span className="fs-icon" aria-hidden="true">
                  {isFullscreen ? (
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M4 14h6v6m10-10h-6V4m0 6l7-7M9 15l-7 7" />
                    </svg>
                  ) : (
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
                    </svg>
                  )}
                </span>
                <span className="fs-label">{isFullscreen ? "Normal" : "Full Window"}</span>
              </button>
            )}
            <ThemeToggle />
            <button
              type="button"
              className="exit-studio-btn"
              onClick={handleExitStudio}
              title="Exit Studio and return to chat"
              aria-label="Exit Studio"
            >
              <span className="exit-icon" aria-hidden="true">✕</span>
              <span className="exit-label">Exit Studio</span>
            </button>
          </div>
        </div>
        <nav className="header-nav" aria-label="Studio navigation">
          <button
            type="button"
            className={viewMode === "lessons" ? "active" : ""}
            onClick={() => changeViewMode("lessons")}
          >
            <span className="nav-tab-icon" aria-hidden="true">📖</span>
            <span className="nav-tab-label">Lessons</span>
          </button>
          <button
            type="button"
            className={viewMode === "quizzes" ? "active" : ""}
            onClick={() => changeViewMode("quizzes")}
          >
            <span className="nav-tab-icon" aria-hidden="true">❓</span>
            <span className="nav-tab-label">Quizzes</span>
          </button>
          <button
            type="button"
            className={viewMode === "courses" ? "active" : ""}
            onClick={() => changeViewMode("courses")}
          >
            <span className="nav-tab-icon" aria-hidden="true">📚</span>
            <span className="nav-tab-label">Courses</span>
          </button>
          <button
            type="button"
            className={viewMode === "publishing" ? "active" : ""}
            onClick={() => changeViewMode("publishing")}
          >
            <span className="nav-tab-icon" aria-hidden="true">📢</span>
            <span className="nav-tab-label">Publishing</span>
          </button>
          <button
            type="button"
            className={viewMode === "calendar" ? "active" : ""}
            onClick={() => changeViewMode("calendar")}
          >
            <span className="nav-tab-icon" aria-hidden="true">📅</span>
            <span className="nav-tab-label">Calendar</span>
          </button>
          <button
            type="button"
            className={viewMode === "settings" ? "active" : ""}
            onClick={() => changeViewMode("settings")}
          >
            <span className="nav-tab-icon" aria-hidden="true">⚙️</span>
            <span className="nav-tab-label">Settings</span>
          </button>
        </nav>
      </header>

      <Toast error={error} notice={notice} onDismiss={() => { setError(""); setNotice(""); }} />

      <div className={`workspace ${isFullWidthView ? "workspace-full" : ""} ${viewMode === "lessons" && lesson ? "has-active-item" : ""} ${viewMode === "quizzes" && quiz ? "has-active-item" : ""}`}>
        {!isFullWidthView && (
          <aside className="studio-sidebar">
            {/* Courses section in sidebar */}
            <div className="sidebar-course-section">
              <div className="sidebar-section-header">
                <span className="eyebrow">COURSE</span>
                <div className="sidebar-header-actions">
                  {selectedCourse && (
                    <>
                      <button
                        type="button"
                        className="sidebar-action-text-btn"
                        onClick={() => {
                          setCourseEditForm({ title: selectedCourse.title, description: selectedCourse.description });
                          setEditingCourse((v) => !v);
                        }}
                        title={editingCourse ? "Cancel editing" : "Edit course title & description"}
                      >
                        {editingCourse ? "Cancel" : "Edit"}
                      </button>
                      <button
                        type="button"
                        className="sidebar-action-text-btn archive"
                        disabled={busy}
                        onClick={toggleCourseArchive}
                        title={selectedCourse.is_archived ? "Restore course" : "Archive course"}
                      >
                        {selectedCourse.is_archived ? "Restore" : "Archive"}
                      </button>
                    </>
                  )}
                  <button
                    type="button"
                    className="sidebar-action-text-btn primary"
                    onClick={() => {
                      setShowNewCourseForm((show) => !show);
                      setCourseMenuOpen(false);
                    }}
                    title="Add new course"
                  >
                    {showNewCourseForm ? "Cancel" : "＋ Course"}
                  </button>
                </div>
              </div>

              {showNewCourseForm && (
                <form className="sidebar-new-course-form" onSubmit={createCourse}>
                  <input
                    aria-label="New course name"
                    placeholder="New course title..."
                    maxLength={120}
                    value={courseForm.title}
                    onChange={(event) => setCourseForm({ ...courseForm, title: event.target.value })}
                    required
                    autoFocus
                  />
                  <div style={{ display: "flex", gap: "6px", marginTop: "6px" }}>
                    <button className="secondary-button" style={{ minHeight: "28px", fontSize: "11.5px", padding: "0 10px" }} disabled={busy}>
                      Create
                    </button>
                    <button
                      type="button"
                      className="ghost-button"
                      style={{ minHeight: "28px", fontSize: "11.5px", padding: "0 8px" }}
                      onClick={() => setShowNewCourseForm(false)}
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}

              <div className="sidebar-course-selector-wrap" ref={courseMenuRef}>
                <button
                  type="button"
                  className={`sidebar-course-trigger ${courseMenuOpen ? "is-open" : ""}`}
                  onClick={() => setCourseMenuOpen((o) => !o)}
                  aria-haspopup="listbox"
                  aria-expanded={courseMenuOpen}
                  title={selectedCourse ? selectedCourse.title : "Select course"}
                >
                  <div className="sidebar-course-trigger-left">
                    <div className="sidebar-course-icon-badge">
                      {selectedCourse?.title ? selectedCourse.title[0].toUpperCase() : "◈"}
                    </div>
                    <div className="sidebar-course-trigger-text">
                      <div className="sidebar-course-title">
                        {selectedCourse ? selectedCourse.title : (visibleCourses.length ? "Select a course" : "No courses")}
                      </div>
                      <div className="sidebar-course-subtitle">
                        {selectedCourse
                          ? `${selectedCourse.lesson_count || 0} ${selectedCourse.lesson_count === 1 ? "lesson" : "lessons"}${selectedCourse.is_archived ? " · archived" : ""}`
                          : (visibleCourses.length ? `${visibleCourses.length} courses available` : "Click ＋ Course to create")}
                      </div>
                    </div>
                  </div>
                  <svg
                    className={`sidebar-course-chevron ${courseMenuOpen ? "is-open" : ""}`}
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                </button>

                {courseMenuOpen && (
                  <div className="sidebar-course-menu" role="listbox" aria-label="Select course">
                    <div className="sidebar-course-menu-list">
                      {visibleCourses.map((c) => {
                        const isCurrent = String(c.id) === String(courseId);
                        return (
                          <button
                            key={c.id}
                            type="button"
                            role="option"
                            aria-selected={isCurrent}
                            className={`sidebar-course-menu-item ${isCurrent ? "is-active" : ""}`}
                            onClick={() => {
                              selectCourse(String(c.id));
                              setCourseMenuOpen(false);
                            }}
                          >
                            <div className="sidebar-course-menu-item-info">
                              <span className="sidebar-course-menu-item-title">
                                {c.title}
                                {c.is_archived && <span className="archived-tag">archived</span>}
                              </span>
                              <span className="sidebar-course-menu-item-meta">
                                {c.lesson_count} {c.lesson_count === 1 ? "lesson" : "lessons"}
                              </span>
                            </div>
                            {isCurrent && (
                              <span className="sidebar-course-menu-check" aria-hidden="true">✓</span>
                            )}
                          </button>
                        );
                      })}
                      {!visibleCourses.length && (
                        <div className="sidebar-course-menu-empty">No courses available</div>
                      )}
                    </div>
                    <div className="sidebar-course-menu-footer">
                      <button
                        type="button"
                        className="sidebar-course-menu-add-btn"
                        onClick={() => {
                          setCourseMenuOpen(false);
                          setShowNewCourseForm(true);
                        }}
                      >
                        ＋ Create new course
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {editingCourse && selectedCourse && (
                <form className="course-edit-inline" onSubmit={saveCourse}>
                  <input
                    aria-label="Course title"
                    maxLength={120}
                    required
                    value={courseEditForm.title}
                    onChange={(event) => setCourseEditForm({ ...courseEditForm, title: event.target.value })}
                  />
                  <textarea
                    aria-label="Course description"
                    maxLength={2000}
                    placeholder="Course description..."
                    value={courseEditForm.description}
                    onChange={(event) => setCourseEditForm({ ...courseEditForm, description: event.target.value })}
                  />
                  <div style={{ display: "flex", gap: "6px" }}>
                    <button className="secondary-button" style={{ minHeight: "28px", fontSize: "11px", padding: "0 8px" }} disabled={busy}>
                      Save
                    </button>
                    <button
                      type="button"
                      className="ghost-button"
                      style={{ minHeight: "28px", fontSize: "11px", padding: "0 8px" }}
                      onClick={() => setEditingCourse(false)}
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}
            </div>

            {/* Lessons or Quizzes navigation in sidebar */}
            {viewMode === "lessons" ? (
              <div className="sidebar-items-section">
                <div className="sidebar-section-header">
                  <span className="eyebrow">LESSONS ({lessons.length})</span>
                  <div style={{ display: "flex", gap: "4px" }}>
                    <button
                      type="button"
                      className="sidebar-action-pill-btn primary"
                      disabled={!courseId || selectedCourse?.is_archived || busy}
                      onClick={createLesson}
                      title="Create new lesson"
                    >
                      ＋ New
                    </button>
                    <button
                      type="button"
                      className="sidebar-action-pill-btn"
                      disabled={!courseId || selectedCourse?.is_archived || busy}
                      onClick={() => setNoteImportOpen((o) => !o)}
                      title="Import from bot notes"
                    >
                      Import
                    </button>
                  </div>
                </div>

                <div className="sidebar-search-wrap">
                  <input
                    type="text"
                    aria-label="Filter lessons"
                    placeholder="Search lessons…"
                    value={lessonQuery}
                    onChange={(e) => setLessonQuery(e.target.value)}
                    disabled={!courseId}
                  />
                </div>

                {noteImportOpen && (
                  <div className="sidebar-import-drawer">
                    <div className="sidebar-import-drawer-header">
                      <strong>Import Bot Note</strong>
                      <button type="button" className="text-button" onClick={() => setNoteImportOpen(false)}>✕</button>
                    </div>
                    <input
                      className="note-search"
                      aria-label="Search bot notes"
                      placeholder="Search notes, subjects..."
                      value={noteQuery}
                      onChange={(e) => setNoteQuery(e.target.value)}
                    />
                    <div className="sidebar-import-drawer-list">
                      {botNotes.map((note) => (
                        <div key={note.id} className="sidebar-import-drawer-item">
                          <div>
                            <strong>{note.title}</strong>
                            <small>{note.subject_name}</small>
                          </div>
                          {note.already_imported ? (
                            <span className="status status-approved">Imported</span>
                          ) : (
                            <button
                              type="button"
                              className="secondary-button"
                              style={{ minHeight: "26px", fontSize: "11px", padding: "0 8px" }}
                              disabled={busy}
                              onClick={() => importBotNote(note.id)}
                            >
                              Import
                            </button>
                          )}
                        </div>
                      ))}
                      {!botNotes.length && <p className="empty-note">No text notes found.</p>}
                    </div>
                  </div>
                )}

                <div className="sidebar-item-list">
                  {lessons.map((item) => (
                    <div
                      key={item.id}
                      className={`sidebar-item-row ${lesson?.id === item.id ? "active" : ""}`}
                      onClick={async () => {
                        if (!await confirmDiscardChanges()) return;
                        run(() => loadLesson(item.id));
                      }}
                    >
                      <div className="sidebar-item-body">
                        <span className="sidebar-item-icon">▤</span>
                        <div className="sidebar-item-texts">
                          <strong className="sidebar-item-title">{item.title}</strong>
                          <span className="sidebar-item-sub">
                            {new Date(item.updated_at).toLocaleDateString()}
                          </span>
                        </div>
                      </div>
                      <div className="sidebar-item-tail">
                        <span className={`status status-${item.status}`}>{item.status}</span>
                        <button
                          type="button"
                          className="duplicate-btn"
                          title="Duplicate lesson"
                          onClick={(event) => {
                            event.stopPropagation();
                            run(async () => {
                              const duplicated = await api(`/api/lessons/${item.id}/duplicate`, {
                                method: "POST",
                              });
                              await loadLessons(courseId, lessonQuery);
                              await loadLesson(duplicated.id);
                            }, "Lesson duplicated.");
                          }}
                        >
                          ⧉
                        </button>
                        <button
                          type="button"
                          className="delete-item-btn"
                          title="Delete lesson"
                          style={{
                            background: "transparent",
                            border: "none",
                            color: "var(--danger, #ef4444)",
                            cursor: "pointer",
                            padding: "2px 5px",
                            fontSize: "13px",
                          }}
                          onClick={(event) => {
                            event.stopPropagation();
                            deleteLesson(item.id);
                          }}
                        >
                          🗑
                        </button>
                      </div>
                    </div>
                  ))}
                  {!lessons.length && (
                    <div className="empty-note" style={{ textAlign: "center", padding: "24px 8px" }}>
                      <p style={{ margin: "0 0 8px", fontSize: "12px", color: "var(--muted)" }}>
                        {lessonQuery ? "No matching lessons." : courseId ? "No lessons yet in this course." : "Choose or create a course."}
                      </p>
                      {courseId && !selectedCourse?.is_archived && (
                        <button
                          type="button"
                          className="secondary-button"
                          style={{ minHeight: "30px", fontSize: "12px" }}
                          onClick={createLesson}
                        >
                          + Create first lesson
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ) : viewMode === "quizzes" ? (
              <div className="sidebar-items-section">
                <div className="sidebar-section-header">
                  <span className="eyebrow">QUIZZES ({quizzes.length})</span>
                  <button
                    type="button"
                    className="sidebar-action-pill-btn primary"
                    disabled={!courseId || selectedCourse?.is_archived || busy}
                    onClick={createQuiz}
                    title="Create new quiz"
                  >
                    ＋ New Quiz
                  </button>
                </div>

                <div className="sidebar-item-list">
                  {quizzes.map((item) => (
                    <div
                      key={item.id}
                      className={`sidebar-item-row ${quiz?.id === item.id ? "active" : ""}`}
                      onClick={() => selectQuiz(item.id)}
                    >
                      <div className="sidebar-item-body">
                        <span className="sidebar-item-icon">?</span>
                        <div className="sidebar-item-texts">
                          <strong className="sidebar-item-title">{item.title}</strong>
                          <span className="sidebar-item-sub">
                            {item.question_count} {item.question_count === 1 ? "question" : "questions"} · {item.difficulty}
                          </span>
                        </div>
                      </div>
                      <div className="sidebar-item-tail">
                        <button
                          type="button"
                          className="delete-item-btn"
                          title="Delete quiz"
                          style={{
                            background: "transparent",
                            border: "none",
                            color: "var(--danger, #ef4444)",
                            cursor: "pointer",
                            padding: "2px 5px",
                            fontSize: "13px",
                          }}
                          onClick={(event) => {
                            event.stopPropagation();
                            deleteQuiz(item.id);
                          }}
                        >
                          🗑
                        </button>
                      </div>
                    </div>
                  ))}
                  {!quizzes.length && (
                    <div className="empty-note" style={{ textAlign: "center", padding: "24px 8px" }}>
                      <p style={{ margin: "0 0 8px", fontSize: "12px", color: "var(--muted)" }}>
                        {courseId ? "No quizzes in this course yet." : "Choose or create a course."}
                      </p>
                      {courseId && !selectedCourse?.is_archived && (
                        <button
                          type="button"
                          className="secondary-button"
                          style={{ minHeight: "30px", fontSize: "12px" }}
                          onClick={createQuiz}
                        >
                          + Create first quiz
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ) : null}

            <div className="sidebar-footer">
              <button
                type="button"
                className="text-button"
                style={{ fontSize: "11px", padding: 0 }}
                onClick={() => setShowArchivedCourses((s) => !s)}
              >
                {showArchivedCourses ? "Hide archived courses" : "Show archived courses"}
              </button>
              <span className="online-dot" title="Backend connected" />
            </div>
          </aside>
        )}

        {viewMode === "courses" ? (
          <div className="courses-hub-container">
            <div className="courses-hub-nav">
              <button
                type="button"
                className={`courses-hub-tab ${coursesTab === "courses" ? "active" : ""}`}
                onClick={() => setCoursesTab("courses")}
              >
                All Courses ({courses.length})
              </button>
              <button
                type="button"
                className={`courses-hub-tab ${coursesTab === "categories" ? "active" : ""}`}
                onClick={() => setCoursesTab("categories")}
              >
                Categories ({categories.length})
              </button>
            </div>

            {coursesTab === "courses" ? (
              <CourseListPage
                courses={courses}
                categories={categories}
                onSelectCourse={(id) => {
                  selectCourse(String(id));
                  setViewMode("lessons");
                }}
                onEditCourse={(course) => {
                  selectCourse(String(course.id));
                  setCourseEditForm({ title: course.title, description: course.description });
                  setEditingCourse(true);
                }}
                onArchiveCourse={(id, isArchived) => {
                  run(async () => {
                    await apiArchiveCourse(id, isArchived);
                    await loadCourses();
                    await loadDashboard();
                  }, isArchived ? "Course archived." : "Course restored.");
                }}
                onDeleteCourse={(id) => {
                  run(async () => {
                    await apiDeleteCourse(id);
                    await loadCourses();
                    await loadDashboard();
                  }, "Course deleted.");
                }}
                busy={busy}
              />
            ) : (
              <CourseCategories
                categories={categories}
                onCreate={createCategory}
                onUpdate={updateCategory}
                onDelete={deleteCategory}
                editingCategoryId={editingCategory?.id}
                setEditingCategoryId={setEditingCategory}
                editForm={categoryEditForm}
                setEditForm={setCategoryEditForm}
                busy={busy}
                confirmAction={confirmAction}
              />
            )}
          </div>
        ) : viewMode === "lessons" ? (
          <section className="studio-main">
            {lesson ? (
              <>
                {/* 1. Top Editor Toolbar */}
                <div className="editor-top-bar">
                  <div className="editor-breadcrumb">
                    <button
                      type="button"
                      className="back-to-list-btn"
                      onClick={async () => {
                        if (!await confirmDiscardChanges()) return;
                        setLesson(null);
                      }}
                      title="Back to lessons list"
                    >
                      ← Lessons
                    </button>
                    <span className="breadcrumb-course">{selectedCourse?.title}</span>
                    <span className="breadcrumb-separator">/</span>
                    <span className="breadcrumb-lesson">{lessonTitle || "Untitled"}</span>
                    <span className={`status status-${lesson.status}`}>{lesson.status}</span>
                    {busy ? (
                      <span className="save-status saving">Saving…</span>
                    ) : hasUnsavedChanges ? (
                      <span className="save-status unsaved">● Unsaved changes</span>
                    ) : lastSavedTime ? (
                      <span className="save-status saved">✓ Saved</span>
                    ) : null}
                  </div>
                  <div className="editor-toolbar-actions">
                    <button
                      type="button"
                      className="danger-button"
                      style={{
                        background: "rgba(239, 68, 68, 0.12)",
                        color: "#ef4444",
                        border: "1px solid rgba(239, 68, 68, 0.3)",
                        padding: "0 10px",
                        minHeight: "32px",
                        borderRadius: "var(--radius-sm, 6px)",
                        fontSize: "12px",
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                      disabled={busy}
                      onClick={() => deleteLesson(lesson.id)}
                      title="Delete this lesson permanently"
                    >
                      🗑 Delete
                    </button>
                    <button
                      type="button"
                      className={`ghost-button ${showTelegramPreview ? "active" : ""}`}
                      disabled={busy}
                      onClick={previewLesson}
                      title={showTelegramPreview ? "Close preview" : "Preview PDF document & Telegram channel post"}
                    >
                      {showTelegramPreview ? "✕ Close preview" : "📄 PDF & Post Preview"}
                    </button>
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={busy || lesson.status === "publishing" || (!hasUnsavedChanges && lesson.status === "draft" && !lastSavedTime)}
                      onClick={() => run(saveLesson, "Draft saved.")}
                      title={hasUnsavedChanges ? "Save your draft changes" : "Draft saved"}
                    >
                      {hasUnsavedChanges ? "● Save draft" : "Save draft"}
                    </button>
                    <button
                      type="button"
                      className="approve-button"
                      disabled={busy || lesson.status === "publishing" || (lesson.status === "approved" && !hasUnsavedChanges)}
                      onClick={approveLesson}
                      title="Approve this version for channel publishing"
                    >
                      {lesson.status === "approved" && !hasUnsavedChanges ? "✓ Approved" : "✓ Approve"}
                    </button>
                    {lesson.status === "failed" || lesson.status === "partial" ? (
                      <button
                        type="button"
                        className="publish-button"
                        disabled={busy}
                        onClick={retryPublish}
                      >
                        ↻ Retry publish
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="publish-button"
                        disabled={busy || lesson.status !== "approved" || hasUnsavedChanges}
                        onClick={() => publishLesson("card")}
                        title={
                          hasUnsavedChanges
                            ? "Approve your changes before publishing"
                            : lesson.status !== "approved"
                              ? "Approve this lesson before publishing"
                              : "Publish announcement card with Academic PDF Reader button to your Telegram channel"
                        }
                      >
                        Publish Card ↗
                      </button>
                    )}
                  </div>
                </div>

                {/* 2. Editor Content Canvas */}
                <div className="editor-content-canvas">
                  <div className="editor-title-container">
                    <input
                      className="studio-title-input"
                      value={lessonTitle}
                      maxLength={160}
                      onChange={(event) => setLessonTitle(event.target.value)}
                      placeholder="Lesson title..."
                    />
                  </div>

                  {/* Mobile switcher for Draft vs Source Material */}
                  <div className="editor-mobile-tabs">
                    <button
                      type="button"
                      className={`editor-mobile-tab ${mobileEditorTab === "draft" ? "active" : ""}`}
                      onClick={() => setMobileEditorTab("draft")}
                    >
                      ✍ Lesson Draft
                    </button>
                    <button
                      type="button"
                      className={`editor-mobile-tab ${mobileEditorTab === "source" ? "active" : ""}`}
                      onClick={() => setMobileEditorTab("source")}
                    >
                      📄 Source Notes {sourceContent.trim() ? "●" : ""}
                    </button>
                  </div>

                  <div className="editor-panes-grid">
                    <div className={`editor-pane-col editor-pane-source ${mobileEditorTab === "source" ? "mobile-show" : "mobile-hide"}`}>
                      <div className="editor-pane-header">
                        <span>Source Material</span>
                        <div style={{ display: "flex", gap: "6px" }}>
                          {sourceContent.trim() && (
                            <button
                              type="button"
                              className="text-button"
                              style={{ fontSize: "11px" }}
                              onClick={async () => {
                                if (content.trim()) {
                                  const ok = await confirmAction({
                                    title: "Replace Draft?",
                                    message: "Copy source notes into draft? Existing draft content will be replaced.",
                                    confirmText: "Replace Draft",
                                    danger: true,
                                  });
                                  if (!ok) return;
                                }
                                const formatted = smartFormatAcademicText(sourceContent);
                                setContent(formatted);
                                if (!lessonTitle.trim() || lessonTitle.toLowerCase().includes("untitled")) {
                                  const derived = cleanTitle(lessonTitle, sourceContent);
                                  if (derived) setLessonTitle(derived);
                                }
                                setMobileEditorTab("draft");
                              }}
                              title="Copy source notes into lesson draft (with auto academic formatting)"
                            >
                              Copy to Draft →
                            </button>
                          )}
                          <small>Preserved notes</small>
                        </div>
                      </div>
                      <textarea
                        className="studio-textarea"
                        value={sourceContent}
                        onChange={(event) => setSourceContent(event.target.value)}
                        placeholder="Paste original reference material or lecture notes here..."
                      />
                    </div>
                    <div className={`editor-pane-col editor-pane-draft ${mobileEditorTab === "draft" ? "mobile-show" : "mobile-hide"}`}>
                      <div className="editor-pane-header">
                        <span>Lesson Draft</span>
                        <small>Formatted for Telegram</small>
                      </div>
                      <FormattingToolbar
                        onFormat={applyFormat}
                        onUploadImage={handleUploadLessonImage}
                        onPasteImage={handlePasteImageFromClipboard}
                        imageUploading={imageUploading}
                        onUndo={handleUndo}
                        onRedo={handleRedo}
                        canUndo={historyStatus.canUndo}
                        canRedo={historyStatus.canRedo}
                        onStandardize={() => {
                          if (!content.trim()) return;
                          pushEditorHistory(content, false);
                          const formatted = smartFormatAcademicText(content);
                          setContent(formatted);
                          const derived = cleanTitle(lessonTitle, content);
                          if (derived && derived !== lessonTitle) {
                            setLessonTitle(derived);
                          }
                          setNotice("Formatted into academic courseware style!");
                        }}
                        activeFormat={formattingActive}
                        linkDialog={linkDialog}
                        onCloseLink={() => {
                          setLinkDialog(null);
                          contentRef.current?.focus();
                        }}
                        onSubmitLink={(text, url, start, end) => {
                          const val = contentRef.current ? contentRef.current.value : content;
                          const res = applyLink(val, start, end, text, url);
                          updateEditorContent(res.value, res.selectionStart, res.selectionEnd);
                          setLinkDialog(null);
                        }}
                        onLinkDialogChange={(field, val) => {
                          setLinkDialog((prev) => (prev ? { ...prev, [field]: val } : null));
                        }}
                      />
                      <textarea
                        ref={contentRef}
                        className="studio-textarea"
                        value={content}
                        onChange={(event) => {
                          pushEditorHistory(content, true);
                          setContent(event.target.value);
                          handleEditorSelectionChange();
                        }}
                        onKeyDown={handleEditorKeyDown}
                        onPaste={handleEditorPaste}
                        onSelect={handleEditorSelectionChange}
                        onClick={handleEditorSelectionChange}
                        onKeyUp={handleEditorSelectionChange}
                        placeholder="Write formatted lesson. Use ## headings, lists, > quotes, and ``` code blocks..."
                      />
                      {(() => {
                        const imgs = [...(content || "").matchAll(/!\[([^\]]*)\]\(([^)]+)\)/g)].map((m, idx) => ({
                          raw: m[0],
                          index: m.index ?? 0,
                          alt: m[1] || `Image ${idx + 1}`,
                          url: m[2],
                        }));
                        if (!imgs.length) return null;
                        return (
                          <div className="editor-image-strip">
                            <span className="editor-image-strip-label">Attached Images ({imgs.length}):</span>
                            <div className="editor-image-strip-list">
                              {imgs.map((img, idx) => (
                                <div key={`${img.url}-${idx}`} className="editor-image-thumb-card">
                                  <img src={img.url} alt={img.alt} />
                                  <button
                                    type="button"
                                    className="editor-image-remove-btn"
                                    title="Remove image from lesson"
                                    aria-label={`Remove ${img.alt}`}
                                    onClick={(e) => {
                                      e.preventDefault();
                                      e.stopPropagation();
                                      const currentVal = contentRef.current ? contentRef.current.value : content;
                                      pushEditorHistory(currentVal, false);
                                      const before = currentVal.slice(0, img.index);
                                      const after = currentVal.slice(img.index + img.raw.length);
                                      const next = (before + after).replace(/\n{3,}/g, "\n\n").trim();
                                      applyEditorSnapshot(next);
                                      setNotice("Image removed from lesson.");
                                    }}
                                  >
                                    ×
                                  </button>
                                </div>
                              ))}
                            </div>
                          </div>
                        );
                      })()}
                    </div>
                  </div>

                  <div style={{ marginTop: "var(--space-3)" }}>
                    <button
                      type="button"
                      className={`ai-assistant-toggle ${aiPanelOpen ? "active" : ""}`}
                      onClick={() => setAiPanelOpen((open) => !open)}
                    >
                      <span>✦ AI Writing Assistant</span>
                      <small>{aiPanelOpen ? "Hide assistant" : "Show assistant"}</small>
                    </button>
                  </div>
                  {aiPanelOpen && lesson && (
                    <AiAssistantPanel
                      lesson={lesson}
                      sourceContent={sourceContent}
                      setSourceContent={setSourceContent}
                      content={content}
                      setContent={setContent}
                      busy={busy}
                    />
                  )}

                  {showTelegramPreview && (
                    <div className="modal-overlay" onClick={() => setShowTelegramPreview(false)}>
                      <div className="telegram-preview-modal-dialog" onClick={(e) => e.stopPropagation()}>
                        <TelegramPreview
                          courseTitle={selectedCourse?.title || lesson?.course_title || "Course"}
                          lessonTitle={lessonTitle}
                          content={content.trim() ? content : sourceContent}
                          parts={preview}
                          onClose={() => setShowTelegramPreview(false)}
                        />
                      </div>
                    </div>
                  )}

                  <section className="history-section">
                    <p className="eyebrow">VERSION & DELIVERY HISTORY</p>
                    {versions.length ? (
                      versions.map((version) => (
                        <div className="history-item" key={version.id}>
                          <strong>Version {version.version_number}</strong>
                          <span>Approved {new Date(version.approved_at).toLocaleString()}</span>
                          <span className={`status status-${version.publish_status || "approved"}`}>
                            {version.publish_status || "approved"}
                          </span>
                          {version.error && <small className="history-error">{version.error}</small>}
                          {version.telegram_message_ids?.length > 0 && (
                            <small>Telegram message IDs: {version.telegram_message_ids.join(", ")}</small>
                          )}
                        </div>
                      ))
                    ) : (
                      <p className="empty-note">Approved versions and delivery results will appear here.</p>
                    )}
                  </section>
                </div>
              </>
            ) : (
              <div className="course-hub-view">
                <div className="course-hub-header">
                  <div className="course-hub-badge">
                    {selectedCourse?.title?.[0]?.toUpperCase() || "◈"}
                  </div>
                  <div>
                    <h2>{selectedCourse ? selectedCourse.title : "Select a Course"}</h2>
                    <p className="muted">
                      {selectedCourse?.description || "Select a lesson from the sidebar or create a new lesson to start drafting."}
                    </p>
                  </div>
                </div>

                <div className="course-hub-actions">
                  <button
                    type="button"
                    className="publish-button"
                    disabled={!courseId || selectedCourse?.is_archived || busy}
                    onClick={createLesson}
                  >
                    ＋ New Lesson
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={!courseId || selectedCourse?.is_archived || busy}
                    onClick={() => setNoteImportOpen(true)}
                  >
                    Import Bot Note
                  </button>
                </div>

                {lessons.length > 0 && (
                  <div className="course-hub-table-wrapper">
                    <table className="publishing-table">
                      <thead>
                        <tr>
                          <th>Lesson</th>
                          <th>Status</th>
                          <th>Last Updated</th>
                          <th style={{ textAlign: "right" }}>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {lessons.map((item) => (
                          <tr key={item.id} className="publishing-row">
                            <td className="publishing-title-cell">
                              <strong>{item.title}</strong>
                            </td>
                            <td>
                              <span className={`status status-${item.status}`}>{item.status}</span>
                            </td>
                            <td className="muted">{new Date(item.updated_at).toLocaleDateString()}</td>
                            <td style={{ textAlign: "right" }}>
                              <button
                                type="button"
                                className="secondary-button"
                                style={{ minHeight: "30px", padding: "0 10px", fontSize: "12px" }}
                                onClick={() => loadLesson(item.id)}
                              >
                                Open Editor
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </section>
        ) : viewMode === "quizzes" ? (
          <section className="studio-main">
            {quiz ? (
              <>
                {/* Quiz Top Toolbar */}
                <div className="editor-top-bar">
                  <div className="editor-breadcrumb">
                    <button
                      type="button"
                      className="back-to-list-btn"
                      onClick={async () => {
                        if (!await confirmDiscardQuizChanges()) return;
                        setQuiz(null);
                      }}
                      title="Back to quizzes list"
                    >
                      ← Quizzes
                    </button>
                    <span className="breadcrumb-course">{quiz.course_title}</span>
                    <span className="breadcrumb-separator">/</span>
                    <span className="breadcrumb-lesson">{quizTitle || "Untitled quiz"}</span>
                    {quiz.latest_version && (
                      <span className={`status status-${quiz.latest_version.status}`}>
                        {quiz.latest_version.status}
                      </span>
                    )}
                    {busy ? (
                      <span className="save-status saving">Saving…</span>
                    ) : hasUnsavedQuizChanges ? (
                      <span className="save-status unsaved">● Unsaved changes</span>
                    ) : lastSavedTime ? (
                      <span className="save-status saved">✓ Saved</span>
                    ) : null}
                  </div>
                  <div className="editor-toolbar-actions">
                    <button
                      type="button"
                      className="danger-button"
                      style={{
                        background: "rgba(239, 68, 68, 0.12)",
                        color: "#ef4444",
                        border: "1px solid rgba(239, 68, 68, 0.3)",
                        padding: "0 10px",
                        minHeight: "32px",
                        borderRadius: "var(--radius-sm, 6px)",
                        fontSize: "12px",
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                      disabled={busy}
                      onClick={() => deleteQuiz(quiz.id)}
                      title="Delete this quiz permanently"
                    >
                      🗑 Delete
                    </button>
                    <button
                      type="button"
                      className="ghost-button"
                      disabled={!quizQuestions.length}
                      onClick={() => setQuizPreviewOpen((open) => !open)}
                      title="Preview how polls appear"
                    >
                      {quizPreviewOpen ? "Close preview" : "👁 Preview polls"}
                    </button>
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={busy}
                      onClick={() => run(saveQuiz, "Quiz draft saved.")}
                    >
                      Save quiz
                    </button>
                    <button
                      type="button"
                      className="approve-button"
                      disabled={
                        busy ||
                        quiz.latest_version?.status === "publishing" ||
                        ((quiz.latest_version?.status === "approved" || quiz.latest_version?.status === "partial") &&
                          latestSnapshotMatchesDraft &&
                          !hasUnsavedQuizChanges)
                      }
                      onClick={approveQuiz}
                    >
                      {quiz.latest_version?.status === "published" ? "✓ Re-approve quiz" : "✓ Approve quiz"}
                    </button>
                    <button
                      type="button"
                      className="publish-button"
                      disabled={busy || !approvedSnapshotMatchesDraft}
                      onClick={publishQuiz}
                    >
                      Publish polls ↗
                    </button>
                  </div>
                </div>

                {/* Quiz Canvas */}
                <div className="editor-content-canvas">
                  <div className="editor-title-container">
                    <input
                      className="studio-title-input"
                      aria-label="Quiz title"
                      maxLength={160}
                      value={quizTitle}
                      onChange={(event) => setQuizTitle(event.target.value)}
                      placeholder="Quiz title..."
                    />
                  </div>

                  <div className="quiz-settings">
                    <label className="field">
                      <span>Difficulty</span>
                      <SearchableSelect
                        value={quizDifficulty}
                        options={DIFFICULTY_OPTIONS}
                        onChange={setQuizDifficulty}
                      />
                    </label>
                    <label className="field">
                      <span>Time limit <small>Optional, minutes</small></span>
                      <input
                        type="number"
                        min="1"
                        max="600"
                        placeholder="No limit"
                        value={quizDuration}
                        onChange={(event) => setQuizDuration(event.target.value)}
                      />
                    </label>
                    <label className="field quiz-instructions-field">
                      <span>Instructions</span>
                      <textarea
                        maxLength={2000}
                        placeholder="Instructions shown before the quiz..."
                        value={quizInstructions}
                        onChange={(event) => setQuizInstructions(event.target.value)}
                      />
                    </label>
                  </div>

                  <div className="quiz-questions-heading">
                    <div>
                      <p className="eyebrow">QUESTION BANK</p>
                      <h3>{quizQuestions.length} Questions</h3>
                    </div>
                    <div className="add-question-controls">
                      <label className="field">
                        <span>New question format</span>
                        <SearchableSelect
                          value={newQuestionType}
                          options={QUESTION_TYPES.map(([value, label]) => ({ value, label }))}
                          onChange={setNewQuestionType}
                          placeholder="Choose format"
                        />
                      </label>
                      <button
                        type="button"
                        className="secondary-button"
                        disabled={busy || !newQuestionType || quizQuestions.length >= 100}
                        onClick={() => addQuizQuestion()}
                      >
                        ＋ Add question
                      </button>
                      <button
                        type="button"
                        className="ghost-button"
                        onClick={() => setQuestionBankOpen((open) => !open)}
                        disabled={busy || !courseId}
                      >
                        Question bank
                      </button>
                    </div>
                  </div>

                  {questionBankOpen && courseId && quiz && (
                    <QuestionBank
                      courseId={courseId}
                      quizId={quiz.id}
                      onQuestionAdded={(quizData) => {
                        setQuizQuestions(quizData.questions);
                        setQuestionBankOpen(false);
                      }}
                      busy={busy}
                      confirmAction={confirmAction}
                    />
                  )}

                  <div className="quiz-question-list">
                    {quizQuestions.map((question, questionIndex) => (
                      <article className="quiz-question-card" key={`${quiz.id}-${questionIndex}`}>
                        <div className="quiz-question-topline">
                          <strong>Question {questionIndex + 1}</strong>
                          <div className="quiz-reorder">
                            <button
                              type="button"
                              aria-label={`Move question ${questionIndex + 1} up`}
                              disabled={questionIndex === 0}
                              onClick={() => moveQuizQuestion(questionIndex, -1)}
                            >
                              ↑
                            </button>
                            <button
                              type="button"
                              aria-label={`Move question ${questionIndex + 1} down`}
                              disabled={questionIndex === quizQuestions.length - 1}
                              onClick={() => moveQuizQuestion(questionIndex, 1)}
                            >
                              ↓
                            </button>
                            <button
                              type="button"
                              className="remove-question"
                              onClick={() => setQuizQuestions((current) => current.filter((_, index) => index !== questionIndex))}
                            >
                              Remove
                            </button>
                          </div>
                        </div>
                        <label className="field">
                          <span>Question text</span>
                          <textarea
                            maxLength={1000}
                            placeholder="Write your quiz question here..."
                            value={question.question_text}
                            onChange={(event) => updateQuizQuestion(questionIndex, { question_text: event.target.value })}
                          />
                        </label>
                        <div className="quiz-question-settings">
                          <label className="field">
                            <span>Question format</span>
                            <SearchableSelect
                              value={question.question_type}
                              options={QUESTION_TYPES.map(([value, label]) => ({ value, label }))}
                              onChange={(value) => changeQuestionType(questionIndex, value)}
                            />
                          </label>
                          <label className="field">
                            <span>Difficulty</span>
                            <SearchableSelect
                              value={question.difficulty}
                              options={DIFFICULTY_OPTIONS}
                              onChange={(value) => updateQuizQuestion(questionIndex, { difficulty: value })}
                            />
                          </label>
                        </div>
                        <div className="quiz-options">
                          <div className="quiz-options-heading">
                            <strong>
                              {question.question_type === "true_false"
                                ? "True / False choices"
                                : "Multiple choice options"}
                            </strong>
                            <small>
                              {question.question_type === "true_false"
                                ? "Select whether True or False is the correct answer"
                                : "Enter choices and select the single correct answer radio button"}
                            </small>
                          </div>

                          {question.question_type === "true_false" ? (
                            <div className="tf-options-grid">
                              {question.options.map((option, optionIndex) => {
                                const isChecked = option.is_correct;
                                return (
                                  <label
                                    key={`${questionIndex}-${optionIndex}`}
                                    className={`tf-option-card ${isChecked ? "is-selected-correct" : ""}`}
                                  >
                                    <input
                                      type="radio"
                                      name={`tf-correct-${quiz.id}-${questionIndex}`}
                                      checked={isChecked}
                                      onChange={() =>
                                        updateQuizOption(questionIndex, optionIndex, { is_correct: true })
                                      }
                                    />
                                    <span className="tf-label">{option.option_text}</span>
                                    {isChecked ? (
                                      <span className="correct-pill">✓ Correct answer</span>
                                    ) : (
                                      <span className="select-pill">Click to select</span>
                                    )}
                                  </label>
                                );
                              })}
                            </div>
                          ) : (
                            <div className="mc-options-list">
                              {question.options.map((option, optionIndex) => {
                                const letter = String.fromCharCode(65 + optionIndex);
                                const isChecked = option.is_correct;
                                return (
                                  <div
                                    className={`quiz-option-row mc-option-row ${isChecked ? "is-selected-correct" : ""}`}
                                    key={`${questionIndex}-${optionIndex}`}
                                  >
                                    <label className="radio-label" title={`Mark choice ${letter} as correct answer`}>
                                      <input
                                        type="radio"
                                        name={`mc-correct-${quiz.id}-${questionIndex}`}
                                        checked={isChecked}
                                        onChange={() =>
                                          updateQuizOption(questionIndex, optionIndex, { is_correct: true })
                                        }
                                      />
                                      <span className="option-letter">{letter}</span>
                                    </label>
                                    <input
                                      aria-label={`Choice ${letter} text`}
                                      maxLength={100}
                                      value={option.option_text}
                                      onChange={(event) =>
                                        updateQuizOption(questionIndex, optionIndex, {
                                          option_text: event.target.value,
                                        })
                                      }
                                      placeholder={`Choice ${letter} text...`}
                                    />
                                    {isChecked && <span className="correct-badge" title="Selected as correct answer">✓ Correct</span>}
                                    <button
                                      type="button"
                                      className="text-button remove-option"
                                      disabled={question.options.length <= 2}
                                      onClick={() =>
                                        updateQuizQuestion(questionIndex, {
                                          options: question.options.filter((_, index) => index !== optionIndex),
                                        })
                                      }
                                      title={`Remove choice ${letter}`}
                                      aria-label={`Remove choice ${letter}`}
                                    >
                                      ×
                                    </button>
                                  </div>
                                );
                              })}
                              {question.options.length < 10 && (
                                <button
                                  type="button"
                                  className="text-button add-option"
                                  onClick={() =>
                                    updateQuizQuestion(questionIndex, {
                                      options: [
                                        ...question.options,
                                        { option_text: "", match_text: null, is_correct: false },
                                      ],
                                    })
                                  }
                                >
                                  ＋ Add choice ({String.fromCharCode(65 + question.options.length)})
                                </button>
                              )}
                            </div>
                          )}
                        </div>
                        <label className="field">
                          <span>Answer explanation <small>Shown after answering poll in Telegram</small></span>
                          <textarea
                            maxLength={200}
                            placeholder="Explain why the answer is correct (optional, max 200 chars for Telegram)"
                            value={question.explanation}
                            onChange={(event) => updateQuizQuestion(questionIndex, { explanation: event.target.value })}
                          />
                        </label>
                      </article>
                    ))}
                    {!quizQuestions.length && (
                      <p className="empty-note">
                        Add a question to start building this quiz. You can save the quiz details first and add questions later.
                      </p>
                    )}
                  </div>

                  <section className="quiz-delivery-status" aria-live="polite">
                    <div>
                      <p className="eyebrow">APPROVAL & CHANNEL DELIVERY</p>
                      {quiz.latest_version ? (
                        <p>
                          Version {quiz.latest_version.version_number} ·{" "}
                          <span className={`status status-${quiz.latest_version.status}`}>
                            {quiz.latest_version.status}
                          </span>
                          {quiz.latest_version.status === "approved" && !approvedSnapshotMatchesDraft
                            ? " · Saved quiz differs from approved version; approve it again."
                            : quiz.latest_version.status === "partial" && !latestSnapshotMatchesDraft
                              ? " · Edit and approve a new version before publishing again."
                              : ""}
                        </p>
                      ) : (
                        <p className="muted small">Preview and save your quiz, then approve it before publishing.</p>
                      )}
                      {quiz.latest_version?.error && (
                        <p className="history-error">{quiz.latest_version.error}</p>
                      )}
                      {quiz.latest_version?.telegram_message_ids?.length > 0 && (
                        <p className="muted small">
                          Telegram message IDs: {quiz.latest_version.telegram_message_ids.join(", ")}
                        </p>
                      )}
                    </div>
                    {quizVersions.length > 0 && (
                      <div className="quiz-version-history">
                        <strong>Version history</strong>
                        {quizVersions.map((version) => (
                          <span key={version.id}>
                            v{version.version_number} · {version.status}
                            {version.telegram_message_ids?.length
                              ? ` · ${version.telegram_message_ids.length} Telegram messages`
                              : ""}
                          </span>
                        ))}
                      </div>
                    )}
                    <p className="muted small">
                      Publishing sends interactive Telegram quiz polls with live countdown timers directly to your linked channel.
                    </p>
                  </section>

                  {quizPreviewOpen && (
                    <section className="quiz-preview">
                      <p className="eyebrow">QUIZ PREVIEW · TELEGRAM POLLS & ANSWER KEY</p>
                      <h3>{quizTitle}</h3>
                      {quizInstructions && quizInstructions.trim().toLowerCase() !== (quizQuestions[0]?.question_text || "").trim().toLowerCase() && (
                        <p className="muted">{quizInstructions}</p>
                      )}
                      <p className="quiz-preview-meta">
                        {quizDifficulty}
                        {quizDuration ? ` · ⏱ ${quizDuration} min live countdown` : ""}
                      </p>
                      {quizQuestions.map((question, index) => (
                        <article className="quiz-preview-question" key={`preview-${index}`}>
                          <div className="preview-question-header">
                            <strong>{index + 1}. {question.question_text || "Untitled question"}</strong>
                            <span className="format-badge">
                              {question.question_type === "true_false" ? "True / False Poll" : "Multiple Choice Poll"}
                            </span>
                          </div>
                          <ul className="preview-options-list">
                            {question.options.map((option, optionIndex) => {
                              const prefix = question.question_type === "multiple_choice"
                                ? `${String.fromCharCode(65 + optionIndex)}. `
                                : "";
                              return (
                                <li className={`preview-option-item ${option.is_correct ? "correct-answer" : ""}`} key={optionIndex}>
                                  <span className="preview-opt-name">
                                    {prefix}{option.option_text || `Choice ${optionIndex + 1}`}
                                  </span>
                                  {option.is_correct && <span className="correct-badge">✓ Correct</span>}
                                </li>
                              );
                            })}
                          </ul>
                          {question.explanation && <p className="muted"><b>Explanation:</b> {question.explanation}</p>}
                        </article>
                      ))}
                    </section>
                  )}
                </div>
              </>
            ) : (
              <div className="course-hub-view">
                <div className="course-hub-header">
                  <div className="course-hub-badge">?</div>
                  <div>
                    <h2>{selectedCourse ? selectedCourse.title + " Quizzes" : "Select a Course"}</h2>
                    <p className="muted">
                      Create interactive multiple-choice and true/false polls for your Telegram channel.
                    </p>
                  </div>
                </div>

                <div className="course-hub-actions">
                  <button
                    type="button"
                    className="publish-button"
                    disabled={!courseId || selectedCourse?.is_archived || busy}
                    onClick={createQuiz}
                  >
                    ＋ New Quiz
                  </button>
                </div>

                {quizzes.length > 0 && (
                  <div className="course-hub-table-wrapper">
                    <table className="publishing-table">
                      <thead>
                        <tr>
                          <th>Quiz Title</th>
                          <th>Difficulty</th>
                          <th>Questions</th>
                          <th>Time Limit</th>
                          <th style={{ textAlign: "right" }}>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {quizzes.map((item) => (
                          <tr key={item.id} className="publishing-row">
                            <td className="publishing-title-cell">
                              <strong>{item.title}</strong>
                            </td>
                            <td>
                              <span className="status">{item.difficulty}</span>
                            </td>
                            <td className="muted">{item.question_count} questions</td>
                            <td className="muted">{item.duration_minutes ? `${item.duration_minutes} min` : "No limit"}</td>
                            <td style={{ textAlign: "right" }}>
                              <button
                                type="button"
                                className="secondary-button"
                                style={{ minHeight: "30px", padding: "0 10px", fontSize: "12px" }}
                                onClick={() => selectQuiz(item.id)}
                              >
                                Open in Builder
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>

                  </div>
                )}
              </div>
            )}
          </section>
        ) : viewMode === "publishing" ? (
          <PublishingManager
            busy={busy}
            onOpenLesson={(lessonId, cId) => {
              if (cId) selectCourse(String(cId));
              loadLesson(lessonId);
              setViewMode("lessons");
            }}
            onOpenCalendar={() => setViewMode("calendar")}
          />
        ) : viewMode === "calendar" ? (
          <PublishingCalendar
            busy={busy}
            confirmAction={confirmAction}
            onNavigateLesson={(lessonId) => {
              loadLesson(lessonId);
              setViewMode("lessons");
            }}
          />
        ) : viewMode === "settings" ? (
          <SettingsPage admin={admin} busy={busy} />
        ) : null}
      </div>
      <footer className="app-footer">CyberLearn Studio <span>·</span> Human-reviewed publishing</footer>

      {confirmDialog && (
        <div
          className="modal-overlay confirm-modal-overlay"
          onClick={confirmDialog.onCancel}
          role="presentation"
        >
          <div
            className="modal confirm-modal"
            onClick={(e) => e.stopPropagation()}
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="confirm-dialog-title"
            aria-describedby="confirm-dialog-desc"
          >
            <div className="confirm-modal-header">
              <div className={`confirm-modal-icon ${confirmDialog.danger ? "danger" : "info"}`}>
                {confirmDialog.danger ? (
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                    <line x1="12" y1="9" x2="12" y2="13" />
                    <line x1="12" y1="17" x2="12.01" y2="17" />
                  </svg>
                ) : (
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="16" x2="12" y2="12" />
                    <line x1="12" y1="8" x2="12.01" y2="8" />
                  </svg>
                )}
              </div>
              <div className="confirm-modal-texts">
                <h3 id="confirm-dialog-title">{confirmDialog.title}</h3>
                <p id="confirm-dialog-desc">{confirmDialog.message}</p>
              </div>
            </div>
            <div className="modal-actions confirm-modal-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={confirmDialog.onCancel}
              >
                {confirmDialog.cancelText || "Cancel"}
              </button>
              <button
                type="button"
                className={`confirm-action-btn ${confirmDialog.danger ? "danger-button" : "primary-button"}`}
                onClick={confirmDialog.onConfirm}
                autoFocus
              >
                {confirmDialog.confirmText || "Confirm"}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

export default App;
