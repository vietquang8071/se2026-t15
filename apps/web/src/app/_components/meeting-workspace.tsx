"use client";

import Link from "next/link";
import { useState } from "react";
import Icon from "./icon";
import MeetingUploadForm from "./meeting-upload-form";
import type { MeetingDraft } from "./meeting-upload-form";
import SampleMinutes from "./sample-minutes";
import type { MeetingContext } from "./sample-minutes";
import { Brand, ThemeToggle } from "./ui";

export default function MeetingWorkspace() {
  const [view, setView] = useState<"upload" | "minutes">("upload");
  const [draft, setDraft] = useState<MeetingDraft>({
    title: "",
    date: "",
    participants: "",
    file: null,
  });
  const [meeting, setMeeting] = useState<MeetingContext | null>(null);

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
          <Brand />
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
        <div className="sidebar-account">
          <p className="sidebar-account-label">Khám phá bản demo</p>
          <Link href="/sign-in">Đăng nhập</Link>
          <Link href="/sign-up">Tạo tài khoản</Link>
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
            <span className="demo-badge">Bản demo</span>
            <ThemeToggle />
            <Link className="header-auth-link" href="/sign-in">
              Đăng nhập
            </Link>
          </div>
        </header>

        <main
          className={`main-content${view === "minutes" ? " main-content-minutes" : " main-content-upload"}`}
        >
          {view === "upload" ? (
            <>
              <div className="page-heading">
                <div>
                  <p className="eyebrow">Không gian làm việc</p>
                  <h1 className="page-title">Tạo biên bản mới</h1>
                  <p className="page-description">
                    Bắt đầu từ file audio cuộc họp. Xem cách nội dung được sắp
                    xếp thành một bộ biên bản rõ ràng.
                  </p>
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
