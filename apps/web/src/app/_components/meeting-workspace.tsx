"use client";

import { useEffect, useState } from "react";
import Icon from "./icon";
import MeetingUploadForm from "./meeting-upload-form";
import type { MeetingDraft } from "./meeting-upload-form";
import SampleMinutes from "./sample-minutes";
import type { MeetingContext } from "./sample-minutes";

type Theme = "light" | "dark";
const themeStorageKey = "meeting-minutes-theme";

export default function MeetingWorkspace() {
  const [view, setView] = useState<"upload" | "minutes">("upload");
  const [draft, setDraft] = useState<MeetingDraft>({
    title: "",
    date: "",
    participants: "",
    file: null,
  });
  const [meeting, setMeeting] = useState<MeetingContext | null>(null);

  useEffect(() => {
    let savedTheme: string | null = null;
    try {
      savedTheme = window.localStorage.getItem(themeStorageKey);
    } catch {
      savedTheme = null;
    }

    const initialTheme: Theme =
      savedTheme === "light" || savedTheme === "dark"
        ? savedTheme
        : window.matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light";

    document.documentElement.dataset.theme = initialTheme;
  }, []);

  function toggleTheme() {
    const hasDarkPreference = window.matchMedia(
      "(prefers-color-scheme: dark)",
    ).matches;
    const currentTheme: Theme =
      document.documentElement.dataset.theme === "dark" ||
      (document.documentElement.dataset.theme !== "light" && hasDarkPreference)
        ? "dark"
        : "light";
    const nextTheme: Theme = currentTheme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = nextTheme;
    try {
      window.localStorage.setItem(themeStorageKey, nextTheme);
    } catch {
      // Keep the theme active for this session when storage is unavailable.
    }
  }

  function createMinutes(nextDraft: MeetingDraft) {
    setDraft(nextDraft);
    setMeeting({
      title: nextDraft.title.trim(),
      date: nextDraft.date,
      participants: nextDraft.participants
        .split(",")
        .map((person) => person.trim())
        .filter(Boolean),
    });
    setView("minutes");
  }

  function startNewMeeting() {
    setView("upload");
    setMeeting(null);
    setDraft({ title: "", date: "", participants: "", file: null });
  }

  return (
    <div
      className={`workspace${view === "minutes" ? " workspace-minutes" : " workspace-upload"}`}
    >
      <aside className="sidebar">
        <div className="sidebar-main">
          <div className="brand">
            <span className="brand-mark">
              <Icon name="document" size={19} />
            </span>
            <div>
              <p className="brand-name">Meeting Minutes</p>
              <p className="brand-caption">WORKSPACE</p>
            </div>
          </div>
          <button
            className="new-meeting-button"
            type="button"
            onClick={startNewMeeting}
          >
            <Icon name="plus" size={15} /> Tạo cuộc họp
          </button>
        </div>

        <div>
          <p className="sidebar-section-label">Không gian làm việc</p>
          <nav className="nav-list" aria-label="Điều hướng chính">
            <button
              className="nav-item"
              type="button"
              aria-current={view === "upload" ? "page" : undefined}
              onClick={startNewMeeting}
            >
              <Icon name="document" size={16} /> Cuộc họp mới
            </button>
            {view === "minutes" && (
              <button
                className="nav-item"
                type="button"
                aria-current="page"
                onClick={() => setView("minutes")}
              >
                <Icon name="file" size={16} /> Biên bản
              </button>
            )}
          </nav>
        </div>

        <div className="sidebar-note">
          <p className="sidebar-note-title">
            <Icon name="upload" size={14} /> Tải audio có sẵn
          </p>
          <p className="sidebar-note-copy">
            MP3, M4A, WAV, WebM
            <br />
            Tối đa 100 MB mỗi file
          </p>
        </div>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <div className="breadcrumbs" aria-label="Đường dẫn">
            <span>Workspace</span>
            <Icon name="chevron-right" size={13} />
            <span className="breadcrumbs-current">
              {view === "minutes" ? "Biên bản" : "Cuộc họp mới"}
            </span>
          </div>
          <div className="topbar-actions">
            <button
              className="theme-toggle"
              type="button"
              aria-label="Chuyển giao diện sáng hoặc tối"
              title="Chuyển giao diện sáng hoặc tối"
              onClick={toggleTheme}
            >
              <span className="theme-icon-light">
                <Icon name="moon" size={17} />
              </span>
              <span className="theme-icon-dark">
                <Icon name="sun" size={17} />
              </span>
            </button>
            <span className="account-avatar" aria-label="Tài khoản mẫu">
              MM
            </span>
          </div>
        </header>

        <main
          className={`main-content${view === "minutes" ? " main-content-minutes" : " main-content-upload"}`}
        >
          {view === "upload" ? (
            <>
              <div className="page-heading">
                <div>
                  <h1 className="page-title">Tạo biên bản mới</h1>
                </div>
                <span className="step-indicator">
                  <span className="step-dot" /> Bước 1 / 2
                </span>
              </div>
              <MeetingUploadForm
                draft={draft}
                onDraftChange={setDraft}
                onSubmit={createMinutes}
              />
            </>
          ) : meeting ? (
            <SampleMinutes meeting={meeting} />
          ) : null}
        </main>
      </div>
    </div>
  );
}
