import { createContext, useContext, useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "cyberlearn-theme";
export const THEMES = ["light", "dark", "system"];

function getSavedTheme(defaultTheme = "dark") {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "light" || saved === "dark") {
      return saved;
    }
  } catch (e) {
    // ignore
  }
  return defaultTheme;
}

export function resolveTheme(theme) {
  if (theme === "light") {
    return "light";
  }
  // Default to true black dark theme
  return "dark";
}

export function applyTheme(theme) {
  const resolved = resolveTheme(theme);
  const color = resolved === "light" ? "#f3efe6" : "#090910";
  if (typeof document !== "undefined") {
    document.documentElement.setAttribute("data-theme", resolved);
    document.documentElement.style.colorScheme = resolved;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute("content", color);
    }
  }
  if (typeof window !== "undefined" && window.Telegram?.WebApp) {
    const tg = window.Telegram.WebApp;
    try {
      if (typeof tg.setHeaderColor === "function") {
        tg.setHeaderColor(color);
      }
      if (typeof tg.setBackgroundColor === "function") {
        tg.setBackgroundColor(color);
      }
    } catch (e) {}
  }
  return resolved;
}

const ThemeContext = createContext({
  theme: "dark",
  resolvedTheme: "dark",
  setTheme: () => {},
  themes: THEMES,
});

export function ThemeProvider({ children, initialTheme = "dark" }) {
  const [theme, setThemeState] = useState(() => getSavedTheme(initialTheme));
  const [resolvedTheme, setResolvedTheme] = useState(() => resolveTheme(getSavedTheme(initialTheme)));

  useEffect(() => {
    // Apply current theme on mount
    const resolved = applyTheme(theme);
    setResolvedTheme(resolved);

    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");

    const handler = () => {
      if (theme === "system") {
        const nextResolved = mq.matches ? "dark" : "light";
        setResolvedTheme(nextResolved);
        applyTheme("system");
      }
    };

    if (mq.addEventListener) {
      mq.addEventListener("change", handler);
      return () => mq.removeEventListener("change", handler);
    } else if (mq.addListener) {
      mq.addListener(handler);
      return () => mq.removeListener(handler);
    }
  }, [theme]);

  const setTheme = (next) => {
    if (!THEMES.includes(next)) return;
    setThemeState(next);
    const resolved = applyTheme(next);
    setResolvedTheme(resolved);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch (e) {
      // ignore
    }
  };

  const value = useMemo(
    () => ({ theme, resolvedTheme, setTheme, themes: THEMES }),
    [theme, resolvedTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  return useContext(ThemeContext);
}

export default ThemeContext;
