"use client";

import { useRef, useState } from "react";
import type { ChangeEvent, DragEvent, FormEvent } from "react";
import Icon from "./icon";
import { Button, TextField } from "./ui";

export const MAX_UPLOAD_SIZE_BYTES = 100 * 1024 * 1024;

const supportedExtensions = ["mp3", "m4a", "wav", "webm"];

export type MeetingDraft = {
  title: string;
  date: string;
  participants: string;
  file: File | null;
};

export function isSupportedAudioFile(file: File): string | null {
  const extension = file.name.split(".").pop()?.toLowerCase();

  if (!extension || !supportedExtensions.includes(extension)) {
    return "Định dạng chưa được hỗ trợ. Hãy chọn file MP3, M4A, WAV hoặc WebM.";
  }

  const mimeType = file.type.toLowerCase();
  const typeIsUnknown = !mimeType || mimeType === "application/octet-stream";
  const typeLooksLikeAudio =
    mimeType.startsWith("audio/") ||
    (extension === "webm" && mimeType === "video/webm");

  if (!typeIsUnknown && !typeLooksLikeAudio) {
    return "File đã chọn không có định dạng audio phù hợp. Hãy chọn file audio khác.";
  }

  return null;
}

function formatFileSize(size: number) {
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(0)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export default function MeetingUploadForm({
  draft,
  onDraftChange,
  onSubmit,
}: {
  draft: MeetingDraft;
  onDraftChange: (draft: MeetingDraft) => void;
  onSubmit: (draft: MeetingDraft) => void;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<{
    title?: string;
    date?: string;
    file?: string;
  }>({});

  function selectFile(file: File | undefined) {
    if (!file) return;

    if (file.size > MAX_UPLOAD_SIZE_BYTES) {
      onDraftChange({ ...draft, file: null });
      setFileError("File vượt quá giới hạn 100 MB. Hãy chọn file nhỏ hơn.");
      setFieldErrors((current) => ({
        ...current,
        file: "Vui lòng chọn file audio tối đa 100 MB.",
      }));
      return;
    }

    if (file.size === 0) {
      onDraftChange({ ...draft, file: null });
      setFileError("File đang trống. Hãy chọn một file audio khác.");
      setFieldErrors((current) => ({
        ...current,
        file: "File audio không được để trống.",
      }));
      return;
    }

    const error = isSupportedAudioFile(file);
    if (error) {
      onDraftChange({ ...draft, file: null });
      setFileError(error);
      setFieldErrors((current) => ({ ...current, file: error }));
      return;
    }

    onDraftChange({ ...draft, file });
    setFileError(null);
    setFieldErrors((current) => ({ ...current, file: undefined }));
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    selectFile(event.target.files?.[0]);
    event.target.value = "";
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    selectFile(event.dataTransfer.files[0]);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextErrors: typeof fieldErrors = {};

    if (!draft.title.trim())
      nextErrors.title = "Nhập tên cuộc họp để tiếp tục.";
    if (!draft.date) nextErrors.date = "Chọn ngày diễn ra cuộc họp.";
    if (!draft.file)
      nextErrors.file = fileError ?? "Chọn file audio có sẵn để tiếp tục.";

    setFieldErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;

    onSubmit(draft);
  }

  function clearSelectedFile() {
    onDraftChange({ ...draft, file: null });
    setFileError(null);
    setFieldErrors((current) => ({ ...current, file: undefined }));
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  return (
    <form className="form-card" onSubmit={handleSubmit} noValidate>
      <div className="card-heading">
        <span className="card-heading-icon">
          <Icon name="document" size={17} />
        </span>
        <div>
          <h2 className="card-title">Thông tin cuộc họp</h2>
          <p className="card-subtitle">
            Nhập thông tin cơ bản và thêm file audio đã có.
          </p>
        </div>
      </div>

      <div className="field-grid">
        <TextField
          id="meeting-title"
          label="Tên cuộc họp"
          fullWidth
          type="text"
          placeholder="Ví dụ: Họp kế hoạch sản phẩm tháng 10"
          value={draft.title}
          required
          error={fieldErrors.title}
          onChange={(event) => {
            onDraftChange({ ...draft, title: event.target.value });
            setFieldErrors((current) => ({ ...current, title: undefined }));
          }}
        />

        <TextField
          id="meeting-date"
          label="Ngày họp"
          type="date"
          value={draft.date}
          required
          error={fieldErrors.date}
          onChange={(event) => {
            onDraftChange({ ...draft, date: event.target.value });
            setFieldErrors((current) => ({ ...current, date: undefined }));
          }}
        />

        <TextField
          id="meeting-participants"
          label="Người tham gia"
          type="text"
          placeholder="Tên người, cách nhau bằng dấu phẩy"
          value={draft.participants}
          hint="Có thể bổ sung hoặc chỉnh sửa sau."
          onChange={(event) =>
            onDraftChange({ ...draft, participants: event.target.value })
          }
        />

        <div className="field field-full">
          <span className="field-label" id="audio-file-label">
            File audio<span className="field-required">*</span>
          </span>
          <input
            ref={fileInputRef}
            className="visually-hidden-input"
            type="file"
            accept=".mp3,.m4a,.wav,.webm,audio/mpeg,audio/mp4,audio/wav,audio/webm"
            aria-labelledby="audio-file-label"
            aria-describedby={fieldErrors.file ? "file-error" : undefined}
            aria-invalid={Boolean(fieldErrors.file)}
            onChange={handleFileChange}
          />
          <div
            className="dropzone"
            data-dragging={isDragging}
            onDragEnter={(event) => {
              event.preventDefault();
              setIsDragging(true);
            }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={(event) => {
              if (event.currentTarget === event.target) setIsDragging(false);
            }}
            onDrop={handleDrop}
          >
            {draft.file ? (
              <div className="selected-file">
                <span className="file-icon">
                  <Icon name="file" size={18} />
                </span>
                <div className="selected-file-details">
                  <p className="selected-file-name">{draft.file.name}</p>
                  <p className="selected-file-size">
                    {formatFileSize(draft.file.size)}
                  </p>
                </div>
                <button
                  className="icon-button"
                  type="button"
                  aria-label="Xóa file đã chọn"
                  onClick={clearSelectedFile}
                >
                  <Icon name="close" size={16} />
                </button>
              </div>
            ) : (
              <button
                className="dropzone-button"
                type="button"
                onClick={() => fileInputRef.current?.click()}
              >
                <span className="upload-icon">
                  <Icon name="upload" size={18} />
                </span>
                <span className="dropzone-title">
                  <span className="dropzone-link">Chọn file</span> hoặc kéo thả
                  vào đây
                </span>
                <span className="dropzone-detail">
                  MP3, M4A, WAV hoặc WebM · tối đa 100 MB
                </span>
              </button>
            )}
          </div>
          {(fieldErrors.file || fileError) && (
            <p id="file-error" className="field-error" role="alert">
              {fieldErrors.file ?? fileError}
            </p>
          )}
        </div>
      </div>

      <div className="form-footer">
        <p className="local-note">
          <Icon name="info" size={14} />
          Đây là bản xem trước giao diện. File được chọn chỉ nằm trong trình
          duyệt; nội dung biên bản bên dưới là dữ liệu mẫu.
        </p>
        <Button type="submit">
          Xem biên bản mẫu <Icon name="chevron-right" size={15} />
        </Button>
      </div>
    </form>
  );
}
