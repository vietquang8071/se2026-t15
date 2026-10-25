# Meeting Minutes Frontend Implementation Plan

> **For agentic workers:** Implement each task in order, keeping the work in the current frontend feature branch.

**Goal:** Replace the starter page with a responsive, client-only upload-to-sample-minutes flow, capped at 100 MB, with light and dark themes.

**Architecture:** Keep `page.tsx` as the App Router entry and put interactive workspace, upload form, sample document, and fixture data in focused frontend files. Use local React state and browser APIs only; do not call the API, upload the selected file, or implement document downloads.

**Tech Stack:** Next.js 16 App Router, React 19, TypeScript, Tailwind CSS 4, existing dependencies only.

**Spec:** `docs/frontend/meeting-minutes-frontend-design.md`

## Global Constraints

- Audio input is an existing MP3, M4A, WAV, or WebM file; no in-browser recording.
- Accept files up to `100 * 1024 * 1024` bytes and reject larger files before submission.
- The selected file stays local; sample minutes are clearly labeled and are not derived from the file.
- Provide light and dark themes, initially following system preference, and persist the selected theme locally.
- Keep all implementation in `apps/web`; add no dependencies or backend behavior.

## Review Focus

- File exactly at 100 MiB is accepted; one byte over is rejected with a clear message.
- Unsupported extensions or clearly non-audio MIME types and empty required fields explain how to recover.
- Drag/drop and file-picker selection show the same file details and validation.
- Newly rendered validation and clipboard errors are announced to assistive technology/users.
- Sample minutes never imply they came from the selected file.
- Transcript and the six document cards use the approved two-column layout with readable type and compact main gutters.
- Global and per-card download controls are visibly present but do not download Markdown or files.
- In the desktop minutes view, only the six-document column scrolls within the viewport; the sidebar stays fixed. Narrow screens use natural page scrolling. No scroll snapping.
- Theme toggle works in both directions, follows system preference before selection, and remembers explicit selection.

---

### Task 1: Build the upload and sample-minutes workspace

**Files:**

- Modify: `apps/web/src/app/page.tsx`
- Modify: `apps/web/src/app/layout.tsx`
- Modify: `apps/web/src/app/globals.css`
- Create: `apps/web/src/app/_components/meeting-workspace.tsx`
- Create: `apps/web/src/app/_components/meeting-upload-form.tsx`
- Create: `apps/web/src/app/_components/sample-minutes.tsx`
- Create: `apps/web/src/lib/sample-minutes.ts`

**Interfaces:**

- `MAX_UPLOAD_SIZE_BYTES = 100 * 1024 * 1024` and `isSupportedAudioFile(file: File): string | null` live in the upload form module; return an error message or `null`.
- `SampleMinutes` fixture data lives in `apps/web/src/lib/sample-minutes.ts`.
- The workspace owns upload/result view state, theme preference, and clipboard action.
- Transcript is a left-column panel; six document cards stack in the right column and each has a disabled download placeholder. The global download placeholder represents all six documents.

- [x] Create the Vietnamese sample fixture with all six business sections and a short speaker-labeled transcript.
- [x] Implement file picker and drag/drop with supported-type, required-field, and 100 MiB validation; show file name and formatted size.
- [x] Build the upload form and clearly labeled sample result view; keep the selected file local and do not simulate transcription progress.
- [x] Add the copy-summary action using the sample fixture.
- [x] Add a responsive CRM-style shell, keyboard-visible focus states, and persistent light/dark toggle using system preference initially.
- [x] Update page metadata and document language for the Vietnamese interface.
- [x] Verify with `pnpm --filter @meeting-minutes/web typecheck`, `pnpm --filter @meeting-minutes/web lint`, and `pnpm --filter @meeting-minutes/web build`.

### Task 2: Refine the sample-minutes layout

**Files:**

- Modify: `apps/web/src/app/_components/sample-minutes.tsx`
- Modify: `apps/web/src/app/_components/meeting-workspace.tsx`
- Modify: `apps/web/src/app/globals.css`
- Modify: `apps/web/src/lib/sample-minutes.ts`

- [x] Put transcript in the full left column and stack the six separate document cards in the right column.
- [x] Add disabled visual download controls to every card and a global “Tải cả bộ” placeholder; remove Markdown download behavior.
- [x] Increase card text size and reduce horizontal page gutters while preserving responsive stacking.
- [x] Verify with `pnpm --filter @meeting-minutes/web typecheck`, `pnpm --filter @meeting-minutes/web lint`, and `pnpm --filter @meeting-minutes/web build`.

### Task 3: Keep scrolling inside the document column

**Files:**

- Modify: `apps/web/src/app/globals.css`
- Modify: `docs/frontend/meeting-minutes-frontend-design.md`

- [ ] Keep the desktop minutes shell at viewport height and scroll only the six-document column; keep the sidebar fixed.
- [ ] Use natural page scrolling on narrow screens and do not add scroll snapping.
- [x] Verify with `pnpm --filter @meeting-minutes/web typecheck`, `pnpm --filter @meeting-minutes/web lint`, and `pnpm --filter @meeting-minutes/web build`.
