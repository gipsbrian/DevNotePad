import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../api/client";
import type { StickyNote } from "../types/api";
import { taskProgress, toggleTask } from "../utils/markdownTasks";
import { useDictation } from "../utils/useDictation";
import {
  IconArchive,
  IconCheckSquare,
  IconChevronLeft,
  IconChevronRight,
  IconListBullet,
  IconMic,
  IconPin,
  IconPlus,
  IconTrash,
  IconX,
  IconNote,
  IconCorner,
  IconSearch,
  IconGrid,
} from "./Icons";

const CORNERS = ["bottom-right", "bottom-left", "top-right", "top-left"] as const;
type Corner = (typeof CORNERS)[number];

/** A note's lines with list bullets and markdown syntax stripped, blanks
 * dropped — plain enough to read at a glance in the wall of notes. */
function plainLines(body: string): string[] {
  return body
    .split("\n")
    .map((l) => l.replace(/^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s*)?/, "").replace(/[#>*_`~]/g, "").trim())
    .filter((l) => l.length > 0);
}

/** The opening words of a note, for a card's title line. */
function firstLine(body: string): string {
  const line = plainLines(body)[0] ?? "";
  return line.length > 44 ? `${line.slice(0, 44).trimEnd()}…` : line || "Empty note";
}

function formatCreated(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const sameDay =
    d.getFullYear() === today.getFullYear() &&
    d.getMonth() === today.getMonth() &&
    d.getDate() === today.getDate();
  return sameDay
    ? `Today, ${d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`
    : d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function StickyColumn({ dashboardId }: { dashboardId: string }) {
  const [notes, setNotes] = useState<StickyNote[]>([]);
  const [showArchived, setShowArchived] = useState(false);
  const [index, setIndex] = useState(0);
  const [editingId, setEditingId] = useState<number | null>(null);
  // A brand-new note is a purely local draft until it has content.
  // Creating it on the server up front left an empty note behind whenever
  // the editor was abandoned (navigating away, reloading), and because
  // notes sort newest-first that blank then covered the real ones.
  const [composing, setComposing] = useState(false);
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Placement and collapsed state persist per board — the panel floats
  // over the columns, so where it sits is a real preference.
  const prefKey = `devnotepad-sticky-${dashboardId}`;
  const [corner, setCorner] = useState<Corner>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(prefKey) || "{}");
      return CORNERS.includes(saved.corner) ? saved.corner : "bottom-right";
    } catch {
      return "bottom-right";
    }
  });
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return JSON.parse(localStorage.getItem(prefKey) || "{}").collapsed ?? false;
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(prefKey, JSON.stringify({ corner, collapsed }));
    } catch {
      // non-critical
    }
  }, [prefKey, corner, collapsed]);

  function cycleCorner() {
    setCorner((c) => CORNERS[(CORNERS.indexOf(c) + 1) % CORNERS.length]);
  }

  const load = useCallback(async () => {
    try {
      const fetched = await api.listStickyNotes(dashboardId, showArchived);
      // Blank notes are artifacts, never content — earlier builds created
      // one on the server the moment "+" was pressed, and because notes
      // sort newest-first an abandoned blank sat on top hiding the real
      // ones. They can't be created any more; this keeps any leftovers
      // out of the stack so the panel always opens on something real.
      const list = fetched.filter((n) => n.body.trim().length > 0);
      setNotes(list);
      setIndex((i) => Math.min(i, Math.max(0, list.length - 1)));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [dashboardId, showArchived]);

  useEffect(() => {
    load();
  }, [load]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? notes.filter((n) => n.body.toLowerCase().includes(q)) : notes;
  }, [notes, query]);

  const draftNote: StickyNote | null = composing
    ? {
        id: -1,
        dashboard_id: dashboardId,
        body: "",
        pinned: false,
        archived: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }
    : null;
  const current = draftNote ?? visible[Math.min(index, Math.max(0, visible.length - 1))];
  const behind = composing ? visible.length : Math.max(0, visible.length - index - 1);

  const dictation = useDictation((text) => {
    setDraft((d) => (d ? `${d}${d.endsWith("\n") ? "" : " "}${text}` : text));
  });

  function addNote() {
    setComposing(true);
    setEditingId(null);
    setDraft("");
    setIndex(0);
  }

  async function saveDraft() {
    const body = draft;

    if (composing) {
      setComposing(false);
      // Nothing typed: nothing was ever created, so there's nothing to
      // clean up either.
      if (!body.trim()) return;
      const note = await api.createStickyNote(dashboardId, body);
      setNotes((prev) => [note, ...prev]);
      setIndex(0);
      return;
    }

    if (editingId === null) return;
    const id = editingId;
    setEditingId(null);
    // Emptying an existing note deletes it rather than leaving a blank.
    if (!body.trim()) {
      await api.deleteStickyNote(dashboardId, id);
      setNotes((prev) => prev.filter((n) => n.id !== id));
      setIndex((i) => Math.max(0, i - 1));
      return;
    }
    const saved = await api.updateStickyNote(dashboardId, id, { body });
    setNotes((prev) => prev.map((n) => (n.id === id ? saved : n)));
  }

  async function patch(note: StickyNote, changes: Parameters<typeof api.updateStickyNote>[2]) {
    await api.updateStickyNote(dashboardId, note.id, changes);
    const list = await api.listStickyNotes(dashboardId, showArchived);
    setNotes(list);

    if (changes.archived !== undefined) {
      // It left this view entirely; stay in range.
      setIndex((i) => Math.max(0, Math.min(i, list.length - 1)));
      return;
    }
    // Pinning re-sorts the stack, so follow the note that was acted on
    // rather than holding an index that now points at a different note.
    const moved = list.findIndex((n) => n.id === note.id);
    setIndex(moved >= 0 ? moved : 0);
  }

  async function removeNote(note: StickyNote) {
    await api.deleteStickyNote(dashboardId, note.id);
    const list = notes.filter((n) => n.id !== note.id);
    setNotes(list);
    setIndex((i) => Math.max(0, Math.min(i, list.length - 1)));
  }

  /** Insert or wrap at the cursor — the small subset of Apple Notes'
   * formatting that markdown covers cleanly. */
  function applyFormat(kind: "bullet" | "task" | "bold") {
    const el = textareaRef.current;
    if (!el) return;
    const { selectionStart: start, selectionEnd: end, value } = el;
    const selected = value.slice(start, end);

    let next: string;
    let caret: number;
    if (kind === "bold") {
      next = `${value.slice(0, start)}**${selected || "bold"}**${value.slice(end)}`;
      caret = start + 2 + (selected || "bold").length;
    } else {
      const prefix = kind === "task" ? "- [ ] " : "- ";
      const atLineStart = start === 0 || value[start - 1] === "\n";
      const lead = atLineStart ? "" : "\n";
      next = `${value.slice(0, start)}${lead}${prefix}${selected}${value.slice(end)}`;
      caret = start + lead.length + prefix.length + selected.length;
    }
    setDraft(next);
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(caret, caret);
    });
  }

  async function handleToggleTask(note: StickyNote, taskIndex: number) {
    const body = toggleTask(note.body, taskIndex);
    setNotes((prev) => prev.map((n) => (n.id === note.id ? { ...n, body } : n)));
    await api.updateStickyNote(dashboardId, note.id, { body });
  }

  const progress = useMemo(() => (current ? taskProgress(current.body) : null), [current]);
  const isEditing = composing || (current && editingId === current.id);

  if (collapsed) {
    return (
      <button
        className={`sticky-tab ${corner}`}
        onClick={() => setCollapsed(false)}
        title="Open sticky notes"
      >
        <IconNote />
        {notes.length > 0 && <span className="sticky-tab-count">{notes.length}</span>}
      </button>
    );
  }

  return (
    <section
      className={`sticky-column floating ${corner}${isEditing ? " editing" : ""}`}
      aria-label="Sticky notes"
    >
      <header className="sticky-head">
        <h3>Sticky notes</h3>
        <div className="sticky-head-actions">
          <button
            className="sticky-icon"
            onClick={cycleCorner}
            title={`Move to another corner (now: ${corner.replace("-", " ")})`}
            aria-label="Move panel to another corner"
          >
            <IconCorner />
          </button>
          <button
            className={`sticky-icon${showArchived ? " on" : ""}`}
            onClick={() => {
              setShowArchived((v) => !v);
              setIndex(0);
              setEditingId(null);
              setComposing(false);
            }}
            title={showArchived ? "Back to active notes" : "View archived notes"}
            aria-pressed={showArchived}
          >
            <IconArchive />
          </button>
          {visible.length > 1 && !composing && (
            <button
              className={`sticky-icon${showAll ? " on" : ""}`}
              onClick={() => setShowAll(true)}
              title="See every note at once"
              aria-label="See every note at once"
            >
              <IconGrid />
            </button>
          )}
          {!showArchived && (
            <button className="sticky-icon" onClick={addNote} title="New sticky note" aria-label="New sticky note">
              <IconPlus />
            </button>
          )}
          <button
            className="sticky-icon"
            onClick={() => setCollapsed(true)}
            title="Collapse"
            aria-label="Collapse sticky notes"
          >
            <IconX />
          </button>
        </div>
      </header>

      {(notes.length > 1 || query) && !composing && (
        <div className="sticky-search">
          <IconSearch />
          <input
            type="search"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setIndex(0);
            }}
            placeholder="Search notes…"
            aria-label="Search sticky notes"
          />
        </div>
      )}

      {error && <p className="sticky-empty">{error}</p>}

      {visible.length === 0 && !composing && !error && (
        <div className="sticky-empty-state">
          <p>
            {query.trim()
              ? `Nothing matches “${query.trim()}”.`
              : showArchived
                ? "Nothing archived yet."
                : "No notes yet."}
          </p>
          {!showArchived && !query.trim() && (
            <button className="btn small" onClick={addNote}>
              <IconPlus /> Add one
            </button>
          )}
        </div>
      )}

      {current && (
        <div className="sticky-stack">
          <div className="sticky-papers">
          {/* The decorative sheets are scoped to their own positioned
              wrapper: spanning the whole stack, they painted above the
              (unpositioned) action buttons and swallowed their clicks. */}

            {behind > 0 && <span className="sticky-paper under-2" aria-hidden />}
            {behind > 1 && <span className="sticky-paper under-1" aria-hidden />}

          <article className={`sticky-paper top${current.pinned ? " pinned" : ""}`}>
            <div className="sticky-meta">
              <time dateTime={current.created_at}>{formatCreated(current.created_at)}</time>
              {progress && progress.total > 0 && (
                <span className="sticky-progress">
                  {progress.done}/{progress.total}
                </span>
              )}
              {current.pinned && <IconPin className="pin-mark" />}
            </div>

            {isEditing ? (
              <>
                <textarea
                  ref={textareaRef}
                  className="sticky-editor"
                  value={draft}
                  autoFocus
                  placeholder="Type a note… markdown works, including - [ ] checklists"
                  onChange={(e) => setDraft(e.target.value)}
                  onBlur={saveDraft}
                />
                <div className="sticky-toolbar">
                  <button onMouseDown={(e) => e.preventDefault()} onClick={() => applyFormat("task")} title="Checklist item">
                    <IconCheckSquare />
                  </button>
                  <button onMouseDown={(e) => e.preventDefault()} onClick={() => applyFormat("bullet")} title="Bullet">
                    <IconListBullet />
                  </button>
                  <button onMouseDown={(e) => e.preventDefault()} onClick={() => applyFormat("bold")} title="Bold">
                    <strong>B</strong>
                  </button>
                  {dictation.supported && (
                    <button
                      className={dictation.listening ? "listening" : ""}
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={dictation.toggle}
                      title={dictation.listening ? "Stop dictation" : "Dictate"}
                    >
                      <IconMic />
                    </button>
                  )}
                  <button className="sticky-done" onMouseDown={(e) => e.preventDefault()} onClick={saveDraft}>
                    Done
                  </button>
                </div>
              </>
            ) : (
              <div
                className="sticky-body markdown-body"
                onDoubleClick={() => {
                  if (showArchived) return;
                  setEditingId(current.id);
                  setDraft(current.body);
                }}
                // Checkbox clicks are handled here rather than per-input:
                // the position of the box among its siblings is exactly the
                // index of the task line in the markdown source.
                onClick={(e) => {
                  const target = e.target as HTMLElement;
                  if (!(target instanceof HTMLInputElement) || target.type !== "checkbox") return;
                  const boxes = Array.from(
                    e.currentTarget.querySelectorAll('input[type="checkbox"]')
                  );
                  const taskIndex = boxes.indexOf(target);
                  if (taskIndex >= 0) handleToggleTask(current, taskIndex);
                }}
                title={showArchived ? undefined : "Double-click to edit"}
              >
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    // react-markdown renders task checkboxes disabled;
                    // enable them so they can be ticked in place.
                    input: (props) => <input {...props} disabled={false} readOnly />,
                  }}
                >
                  {current.body || "_Empty note_"}
                </ReactMarkdown>
              </div>
            )}
          </article>
          </div>

          {!isEditing && (
            <div className="sticky-actions">
              {!showArchived && (
                <>
                  <button
                    className="sticky-icon"
                    onClick={() => patch(current, { pinned: !current.pinned })}
                    title={current.pinned ? "Unpin" : "Pin to top"}
                    aria-pressed={current.pinned}
                  >
                    <IconPin />
                  </button>
                  <button
                    className="sticky-icon"
                    onClick={() => patch(current, { archived: true })}
                    title="Archive this note"
                  >
                    <IconArchive />
                  </button>
                </>
              )}
              {showArchived && (
                <button
                  className="sticky-icon"
                  onClick={() => patch(current, { archived: false })}
                  title="Restore this note"
                >
                  <IconArchive />
                </button>
              )}
              <button className="sticky-icon danger" onClick={() => removeNote(current)} title="Delete permanently">
                <IconTrash />
              </button>
            </div>
          )}

          {!composing && visible.length > 1 && (
            <div className="sticky-pager">
              <button
                className="sticky-icon"
                disabled={index === 0}
                onClick={() => setIndex((i) => Math.max(0, i - 1))}
                aria-label="Previous note"
              >
                <IconChevronLeft />
              </button>
              <span className="sticky-pill" title={`${index + 1} of ${visible.length}`}>
                {behind > 0 ? `+${behind} under` : "last one"}
              </span>
              <button
                className="sticky-icon"
                disabled={index >= visible.length - 1}
                onClick={() => setIndex((i) => Math.min(visible.length - 1, i + 1))}
                aria-label="Next note"
              >
                <IconChevronRight />
              </button>
            </div>
          )}
        </div>
      )}

      {showAll && (
        <NoteWall
          notes={visible}
          currentIndex={Math.min(index, Math.max(0, visible.length - 1))}
          archived={showArchived}
          query={query.trim()}
          onPick={(i) => {
            setIndex(i);
            setShowAll(false);
          }}
          onClose={() => setShowAll(false)}
        />
      )}
    </section>
  );
}

/** Every note laid out at once, over the board. This replaced a deck that
 * fanned open on hover: the pointer rests over the note while you read it,
 * so the deck kept opening over the words unasked. Opening it takes a
 * deliberate click now, and a click picks the note to bring to the top.
 *
 * Portalled because the panel is `overflow: hidden` and would clip it. */
function NoteWall({
  notes,
  currentIndex,
  archived,
  query,
  onPick,
  onClose,
}: {
  notes: StickyNote[];
  currentIndex: number;
  archived: boolean;
  query: string;
  onPick: (index: number) => void;
  onClose: () => void;
}) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return createPortal(
    <div className="note-wall-backdrop" onClick={onClose}>
      <div
        className="note-wall"
        // Four across is as wide as this gets; past that the grid scrolls.
        style={{ ["--cols" as string]: Math.min(notes.length, 4) }}
        role="dialog"
        aria-modal="true"
        aria-label="All sticky notes"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="note-wall-head">
          <h3>
            {archived ? "Archived notes" : "Sticky notes"}
            <span className="note-wall-count">
              {notes.length} {notes.length === 1 ? "note" : "notes"}
              {query ? ` matching “${query}”` : ""}
            </span>
          </h3>
          <button className="sticky-icon" onClick={onClose} title="Close" aria-label="Close">
            <IconX />
          </button>
        </header>

        <p className="note-wall-hint">Click a note to bring it to the top of the stack.</p>

        <div className="note-wall-grid">
          {notes.map((n, i) => {
            const progress = taskProgress(n.body);
            const lines = plainLines(n.body);
            return (
              <button
                key={n.id}
                className={`note-wall-card${i === currentIndex ? " on" : ""}`}
                style={{ ["--i" as string]: Math.min(i, 12) }}
                aria-current={i === currentIndex}
                onClick={() => onPick(i)}
              >
                <span className="note-wall-meta">
                  <time dateTime={n.created_at}>{formatCreated(n.created_at)}</time>
                  {progress.total > 0 && (
                    <span className="sticky-progress">
                      {progress.done}/{progress.total}
                    </span>
                  )}
                  {n.pinned && <IconPin className="pin-mark" />}
                </span>
                <span className="note-wall-title">{firstLine(n.body)}</span>
                {lines.length > 1 && <span className="note-wall-rest">{lines.slice(1).join("\n")}</span>}
              </button>
            );
          })}
        </div>
      </div>
    </div>,
    document.body
  );
}
