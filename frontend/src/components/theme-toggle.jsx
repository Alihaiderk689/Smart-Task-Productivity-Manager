import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/context/ThemeContext";

export default function ThemeToggle({ className = "" }) {
  const { isDark, toggleTheme } = useTheme();

  return (
    <button
      type="button"
      onClick={toggleTheme}
      role="switch"
      aria-checked={isDark}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      className={`relative inline-flex h-8 w-14 shrink-0 items-center rounded-full border border-border bg-muted transition-colors ${className}`}
    >
      <span
        className={`inline-flex h-6 w-6 items-center justify-center rounded-full bg-background shadow-sm transition-transform ${
          isDark ? "translate-x-7" : "translate-x-1"
        }`}
      >
        {isDark ? (
          <Moon className="h-3.5 w-3.5 text-foreground" aria-hidden="true" />
        ) : (
          <Sun className="h-3.5 w-3.5 text-foreground" aria-hidden="true" />
        )}
      </span>
    </button>
  );
}
