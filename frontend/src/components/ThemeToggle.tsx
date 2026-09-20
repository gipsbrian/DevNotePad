import { useEffect, useState } from "react";
import { applyTheme, getStoredTheme, nextTheme, THEME_LABEL, type ThemeChoice } from "../theme";
import { IconMonitor, IconMoon, IconSun } from "./Icons";

const ICON: Record<ThemeChoice, React.ComponentType<React.SVGProps<SVGSVGElement>>> = {
  system: IconMonitor,
  light: IconSun,
  dark: IconMoon,
};

export function ThemeToggle() {
  const [theme, setTheme] = useState<ThemeChoice>("system");

  useEffect(() => {
    const stored = getStoredTheme();
    setTheme(stored);
    applyTheme(stored);
  }, []);

  function cycle() {
    const next = nextTheme(theme);
    setTheme(next);
    applyTheme(next);
  }

  const Icon = ICON[theme];

  return (
    <button className="rail-btn" data-tour="theme" onClick={cycle} title={`Theme: ${THEME_LABEL[theme]}`} aria-label={`Theme: ${THEME_LABEL[theme]}`}>
      <Icon />
    </button>
  );
}
