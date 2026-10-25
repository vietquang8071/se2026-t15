# Meeting Minutes Frontend Design

**Status:** Approved for implementation

## Intent

Replace the Next.js starter screen with the first usable frontend slice for Meeting Minutes Assistant. Focus on the existing-audio upload flow and a sample meeting document; backend integration comes later.

## Selected Flow

1. The user enters a meeting title and date, optionally adds participants, and selects or drops an MP3, M4A, WAV, or WebM file up to 100 MB.
2. The page validates the required fields, file type, and 100 MB size limit, then opens a sample meeting minutes document.
3. The minutes page displays fixture content; the selected file is not uploaded or transcribed in this frontend slice.

## Screens and Content

- **New meeting:** simple form with title, meeting date, optional participants, and a clear upload area showing the selected file and validation errors.
- **Meeting minutes:** place the transcript in a full-height left column, with its heading and note fixed while transcript rows scroll inside the card. Stack six separate document cards in a right column: summary, action items, decisions, open issues, follow-ups, and timeline. Each card has a download control in its upper-right corner.
- Keep a global “Download all six minutes” control in the meeting header. Download controls are visual placeholders only in this slice; do not export Markdown or files yet. Transcript timestamps are illustrative and do not control audio playback.

## Visual and Interaction Direction

Use a restrained CRM style: clear labels, familiar form controls, readable type, neutral surfaces, and one restrained accent color. Keep main-content gutters compact, increase the sample-card body text, avoid decorative gradients and visual clutter. Center the new-meeting form in the available desktop workspace and keep its current content within the viewport. On the minutes screen, keep the workspace within the viewport and scroll the transcript rows and six-document column independently while their headings and the sidebar stay fixed. On narrow screens, return to natural page scrolling. Do not use scroll snapping. Support responsive layouts and keyboard navigation with visible focus states.

Provide both light and dark themes with a visible toggle. Use the system preference initially and remember the user’s selected theme in the browser. Keep contrast readable in both themes.

## Scope and Constraints

- No in-browser recording, microphone capture, API calls, server upload, transcription, meeting persistence, or accounts in this slice.
- The file is selected locally for the demo interaction only. Sample minutes are fixture data.
- Keep implementation in `apps/web`; use the existing Next.js App Router, TypeScript, and Tailwind setup. Do not change the NestJS, Prisma, or database packages.
- Avoid adding dependencies unless the existing stack cannot provide a needed interaction.
