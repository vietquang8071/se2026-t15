"use client";

import Icon from "./icon";
import { SAMPLE_MINUTES } from "@/lib/sample-minutes";

export type MeetingContext = {
  title: string;
  date: string;
  participants: string[];
};

function formatMeetingDate(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(date);
}

function DownloadPlaceholder({ section }: { section: string }) {
  return (
    <button
      className="download-icon-button"
      type="button"
      aria-label={`Tải xuống ${section} (sắp có)`}
      title="Tính năng tải xuống sắp có"
      disabled
    >
      <Icon name="download" size={15} />
    </button>
  );
}

export default function SampleMinutes({
  meeting,
}: {
  meeting: MeetingContext;
}) {
  return (
    <>
      <div className="page-heading minutes-heading">
        <div>
          <p className="eyebrow">Biên bản cuộc họp</p>
          <h1 className="page-title">{meeting.title}</h1>
          <div className="meeting-meta-row">
            <span className="meeting-meta-item">
              <Icon name="calendar" size={14} />
              {formatMeetingDate(meeting.date)}
            </span>
            <span className="meeting-meta-item">
              <Icon name="users" size={14} />
              {meeting.participants.length > 0
                ? meeting.participants.join(", ")
                : "Chưa thêm người tham gia"}
            </span>
          </div>
        </div>
        <div className="minutes-heading-tools">
          <button
            className="secondary-button download-all-placeholder download-placeholder"
            type="button"
            aria-label="Tải toàn bộ sáu biên bản (sắp có)"
            title="Tải thư mục gồm sáu loại biên bản (sắp có)"
            disabled
          >
            <Icon name="download" size={15} /> Tải cả bộ
          </button>
        </div>
      </div>

      <div className="minutes-grid">
        <section
          className="minutes-card transcript-card"
          aria-labelledby="minutes-transcript-title"
        >
          <div className="minutes-card-header">
            <span className="section-number">T</span>
            <h2 className="minutes-card-title" id="minutes-transcript-title">
              Transcript mẫu
            </h2>
          </div>
          <div className="transcript-list">
            {SAMPLE_MINUTES.transcript.map((line) => (
              <div
                className="transcript-line"
                key={`${line.time}-${line.speaker}`}
              >
                <span className="transcript-time">{line.time}</span>
                <span className="transcript-speaker">{line.speaker}</span>
                <span className="transcript-text">{line.text}</span>
              </div>
            ))}
          </div>
          <p className="empty-state-note">
            Mốc thời gian chỉ để minh họa, chưa liên kết với audio.
          </p>
        </section>

        <div className="minutes-documents">
          <section
            className="minutes-card document-card"
            aria-labelledby="minutes-summary-title"
          >
            <div className="minutes-card-header">
              <span className="section-number">01</span>
              <h2 className="minutes-card-title" id="minutes-summary-title">
                Tóm tắt cuộc họp
              </h2>
              <DownloadPlaceholder section="tóm tắt cuộc họp" />
            </div>
            <p className="minutes-copy">{SAMPLE_MINUTES.summary}</p>
          </section>

          <section
            className="minutes-card document-card"
            aria-labelledby="minutes-actions-title"
          >
            <div className="minutes-card-header">
              <span className="section-number">02</span>
              <h2 className="minutes-card-title" id="minutes-actions-title">
                Công việc cần làm
              </h2>
              <DownloadPlaceholder section="công việc cần làm" />
            </div>
            <div className="action-list">
              {SAMPLE_MINUTES.actionItems.map((item) => (
                <div className="action-row" key={item.task}>
                  <p className="action-title">{item.task}</p>
                  <p className="action-owner">Phụ trách: {item.owner}</p>
                  <span className="action-due">Hạn {item.due}</span>
                </div>
              ))}
            </div>
          </section>

          <section
            className="minutes-card document-card"
            aria-labelledby="minutes-decisions-title"
          >
            <div className="minutes-card-header">
              <span className="section-number">03</span>
              <h2 className="minutes-card-title" id="minutes-decisions-title">
                Quyết định
              </h2>
              <DownloadPlaceholder section="quyết định" />
            </div>
            <ul className="minutes-list">
              {SAMPLE_MINUTES.decisions.map((item) => (
                <li className="decision-item" key={item}>
                  <span className="decision-check">
                    <Icon name="check" size={13} />
                  </span>
                  {item}
                </li>
              ))}
            </ul>
          </section>

          <section
            className="minutes-card document-card"
            aria-labelledby="minutes-issues-title"
          >
            <div className="minutes-card-header">
              <span className="section-number">04</span>
              <h2 className="minutes-card-title" id="minutes-issues-title">
                Vấn đề còn mở
              </h2>
              <DownloadPlaceholder section="vấn đề còn mở" />
            </div>
            <ul className="minutes-list">
              {SAMPLE_MINUTES.openIssues.map((item) => (
                <li className="minutes-list-item" key={item}>
                  {item}
                </li>
              ))}
            </ul>
          </section>

          <section
            className="minutes-card document-card"
            aria-labelledby="minutes-followups-title"
          >
            <div className="minutes-card-header">
              <span className="section-number">05</span>
              <h2 className="minutes-card-title" id="minutes-followups-title">
                Việc cần theo dõi
              </h2>
              <DownloadPlaceholder section="việc cần theo dõi" />
            </div>
            <ul className="minutes-list">
              {SAMPLE_MINUTES.followUps.map((item) => (
                <li className="minutes-list-item" key={item}>
                  {item}
                </li>
              ))}
            </ul>
          </section>

          <section
            className="minutes-card document-card"
            aria-labelledby="minutes-timeline-title"
          >
            <div className="minutes-card-header">
              <span className="section-number">06</span>
              <h2 className="minutes-card-title" id="minutes-timeline-title">
                Dòng thời gian
              </h2>
              <DownloadPlaceholder section="dòng thời gian" />
            </div>
            <ol className="timeline-list">
              {SAMPLE_MINUTES.timeline.map((item) => (
                <li
                  className="timeline-item"
                  key={`${item.date}-${item.event}`}
                >
                  <span className="timeline-date">{item.date}</span>
                  <span className="timeline-event">{item.event}</span>
                </li>
              ))}
            </ol>
          </section>
        </div>
      </div>
    </>
  );
}
