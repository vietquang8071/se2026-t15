"use client";

import Link from "next/link";
import { useEffect } from "react";
import type { ButtonHTMLAttributes, InputHTMLAttributes } from "react";
import Icon from "./icon";

const themeStorageKey = "meeting-minutes-theme";

export function Brand() {
  return (
    <Link className="brand" href="/">
      <span className="brand-mark">
        <Icon name="document" size={19} />
      </span>
      <span className="brand-copy">
        <span className="brand-name">Meeting Minutes</span>
        <span className="brand-caption">ASSISTANT</span>
      </span>
    </Link>
  );
}

export function ThemeToggle() {
  useEffect(() => {
    let savedTheme: string | null = null;
    try {
      savedTheme = window.localStorage.getItem(themeStorageKey);
    } catch {
      // Theme preference can still follow the browser setting.
    }
    const theme =
      savedTheme === "light" || savedTheme === "dark"
        ? savedTheme
        : window.matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light";
    document.documentElement.dataset.theme = theme;
  }, []);

  function toggleTheme() {
    const current =
      document.documentElement.dataset.theme === "dark" ? "dark" : "light";
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      window.localStorage.setItem(themeStorageKey, next);
    } catch {
      // Keep the selected theme for this page when storage is unavailable.
    }
  }

  return (
    <button
      className="theme-toggle"
      type="button"
      aria-label="Chuyển giao diện sáng hoặc tối"
      title="Chuyển giao diện sáng hoặc tối"
      onClick={toggleTheme}
    >
      <span className="theme-icon-light">
        <Icon name="moon" size={18} />
      </span>
      <span className="theme-icon-dark">
        <Icon name="sun" size={18} />
      </span>
    </button>
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary";
};

export function Button({
  variant = "primary",
  className = "",
  children,
  ...props
}: ButtonProps) {
  return (
    <button className={`${variant}-button ${className}`.trim()} {...props}>
      {children}
    </button>
  );
}

type TextFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "id"> & {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  fullWidth?: boolean;
};

export function TextField({
  id,
  label,
  hint,
  error,
  required,
  fullWidth,
  className = "",
  ...props
}: TextFieldProps) {
  const describedBy =
    [hint ? `${id}-hint` : null, error ? `${id}-error` : null]
      .filter(Boolean)
      .join(" ") || undefined;
  return (
    <div className={`field${fullWidth ? " field-full" : ""}`}>
      <label className="field-label" htmlFor={id}>
        {label}
        {required && (
          <span className="field-required" aria-hidden="true">
            *
          </span>
        )}
      </label>
      <div className="field-control">
        <input
          id={id}
          className={`text-input ${className}`.trim()}
          required={required}
          aria-required={required || undefined}
          aria-invalid={Boolean(error)}
          aria-describedby={describedBy}
          {...props}
        />
      </div>
      {hint && (
        <p id={`${id}-hint`} className="field-hint">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} className="field-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
