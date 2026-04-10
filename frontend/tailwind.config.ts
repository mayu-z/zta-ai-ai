import type { Config } from "tailwindcss";

const config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        background: "#0a0f1e",
        surface: "#111827",
        "surface-elevated": "#1a2235",
        border: "rgba(255,255,255,0.08)",
        accent: "#6366f1",
        "accent-hover": "#4f46e5",
        success: "#10b981",
        warning: "#f59e0b",
        danger: "#ef4444",
        "text-primary": "#f1f5f9",
        "text-muted": "#64748b",
        "text-faint": "#374151",
      },
      transitionTimingFunction: {
        smooth: "cubic-bezier(0.22, 1, 0.36, 1)",
      },
    },
  },
} satisfies Config;

export default config;
