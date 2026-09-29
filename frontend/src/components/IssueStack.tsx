import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, usePresence } from "framer-motion";
import type { Column, IssueCard } from "../types/api";
import { clearBackdrop, growFromCard, shrinkIntoCard } from "../utils/cardOrigin";
import { IssueDetailModal } from "./IssueDetailModal";
import { IconChevronLeft, IconPlus, IconX } from "./Icons";

/** How many issues can sit side by side. Past three the panes are too
 * narrow for the description to be worth reading. */
export const MAX_OPEN_ISSUES = 3;

/** Takes a closing pane out of the row, so the panes left behind take the
 * space at once, and shrinks it back into its card. */
function leavePane(pane: HTMLElement, issueNumber: number): Promise<unknown> {
  const { offsetLeft, offsetTop, offsetWidth } = pane;
  Object.assign(pane.style, {
    position: "absolute",
    left: `${offsetLeft}px`,
    top: `${offsetTop}px`,
    width: `${offsetWidth}px`,
    pointerEvents: "none",
  });
  return shrinkIntoCard(pane, issueNumber);
}

/** Every pane back to its card while the backdrop clears. */
function leaveStack(overlay: HTMLElement): Promise<unknown> {
  overlay.style.pointerEvents = "none";
  const panes = [...overlay.querySelectorAll<HTMLElement>(".issue-pane-wrap[data-issue]")];
  return Promise.all([
    ...panes.map((pane) => shrinkIntoCard(pane, Number(pane.dataset.issue))),
    clearBackdrop(overlay, 300),
  ]);
}

/** One open issue. Grows out of the card it was opened from, and shrinks
 * back into it when closed on its own. */
function IssuePane({
  issueNumber,
  closing,
  children,
}: {
  issueNumber: number;
  /** Closes already under way, started at the click rather than after the
   * board re-renders, which can take long enough to feel sluggish. */
  closing: Map<number, Promise<unknown>>;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [isPresent, safeToRemove] = usePresence();

  useLayoutEffect(() => {
    if (ref.current) growFromCard(ref.current, issueNumber);
  }, [issueNumber]);

  useEffect(() => {
    if (isPresent) return;
    const pane = ref.current;
    if (!pane) return safeToRemove();
    (closing.get(issueNumber) ?? leavePane(pane, issueNumber)).then(() => {
      closing.delete(issueNumber);
      safeToRemove();
    });
  }, [isPresent, safeToRemove, issueNumber, closing]);

  return (
    <div className="issue-pane-wrap" data-issue={issueNumber} ref={ref}>
      {children}
    </div>
  );
}

export function IssueStack({
  dashboardId,
  issueNumbers,
  columns,
  issuesByColumn,
  onCloseOne,
  onCloseAll,
  onAdd,
  onChanged,
  canWrite = true,
  writeBlockReason = null,
}: {
  dashboardId: string;
  issueNumbers: number[];
  columns: Column[];
  issuesByColumn: Record<number, IssueCard[]>;
  onCloseOne: (issueNumber: number) => void;
  onCloseAll: () => void;
  onAdd: (issueNumber: number) => void;
  onChanged: (closedIssueNumber?: number) => void;
  canWrite?: boolean;
  writeBlockReason?: string | null;
}) {
  const [picking, setPicking] = useState(false);
  const [pickedColumn, setPickedColumn] = useState<Column | null>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const [isPresent, safeToRemove] = usePresence();
  const paneClosing = useRef(new Map<number, Promise<unknown>>()).current;
  const stackClosing = useRef<Promise<unknown> | null>(null);

  // The animations start here, on the click or key, and the removal below
  // waits for them: waiting for the re-render first would add a pause.
  function startLeaving() {
    if (overlayRef.current && !stackClosing.current) stackClosing.current = leaveStack(overlayRef.current);
  }

  function closeAll() {
    startLeaving();
    onCloseAll();
  }

  function closeOne(issueNumber: number) {
    // The last pane takes the whole stack with it.
    if (issueNumbers.length === 1) startLeaving();
    else if (!paneClosing.has(issueNumber)) {
      const pane = overlayRef.current?.querySelector<HTMLElement>(`.issue-pane-wrap[data-issue="${issueNumber}"]`);
      if (pane) paneClosing.set(issueNumber, leavePane(pane, issueNumber));
    }
    onCloseOne(issueNumber);
  }

  useEffect(() => {
    if (isPresent) return;
    const overlay = overlayRef.current;
    if (!overlay) return safeToRemove();
    (stackClosing.current ?? leaveStack(overlay)).then(() => safeToRemove());
  }, [isPresent, safeToRemove]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      // Back out of the picker first — Escape closing the whole
      // comparison because a menu was open would be a rude surprise.
      if (picking) setPicking(false);
      else closeAll();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  useEffect(() => {
    if (!picking) setPickedColumn(null);
  }, [picking]);

  const full = issueNumbers.length >= MAX_OPEN_ISSUES;

  function choose(issueNumber: number) {
    onAdd(issueNumber);
    setPicking(false);
  }

  return (
    <div className="modal-overlay issue-overlay" ref={overlayRef} onClick={closeAll}>
      <div className={`issue-stack count-${issueNumbers.length}`}>
        <AnimatePresence initial={false}>
          {issueNumbers.map((number) => (
            <IssuePane issueNumber={number} key={number} closing={paneClosing}>
              {issueNumbers.length > 1 && (
                <button
                  className="pane-close"
                  onClick={(e) => {
                    e.stopPropagation();
                    closeOne(number);
                  }}
                  title={`Close #${number}`}
                  aria-label={`Close #${number}`}
                >
                  <IconX />
                </button>
              )}
              <IssueDetailModal
                dashboardId={dashboardId}
                issueNumber={number}
                onClose={() => closeOne(number)}
                onChanged={onChanged}
                canWrite={canWrite}
                writeBlockReason={writeBlockReason}
              />
            </IssuePane>
          ))}
        </AnimatePresence>

        {!full && (
          <div className="issue-add" onClick={(e) => e.stopPropagation()}>
            <button
              className="issue-add-btn"
              onClick={() => setPicking((v) => !v)}
              title="Open another issue alongside this one"
              aria-label="Open another issue alongside this one"
              aria-expanded={picking}
            >
              <IconPlus />
            </button>

            {picking && (
              <div className="issue-picker">
                {pickedColumn === null ? (
                  <>
                    <div className="issue-picker-head">Add from which column?</div>
                    <div className="issue-picker-list">
                      {columns.map((column) => {
                        const count = (issuesByColumn[column.id] ?? []).filter(
                          (i) => !issueNumbers.includes(i.number)
                        ).length;
                        return (
                          <button
                            key={column.id}
                            className="issue-picker-row"
                            disabled={count === 0}
                            onClick={() => setPickedColumn(column)}
                          >
                            <span className="picker-name">{column.name}</span>
                            <span className="picker-count">{count}</span>
                          </button>
                        );
                      })}
                      {columns.length === 0 && (
                        <p className="empty-hint">This board has no columns yet.</p>
                      )}
                    </div>
                  </>
                ) : (
                  <>
                    <button className="issue-picker-back" onClick={() => setPickedColumn(null)}>
                      <IconChevronLeft /> {pickedColumn.name}
                    </button>
                    <div className="issue-picker-list">
                      {(issuesByColumn[pickedColumn.id] ?? [])
                        .filter((i) => !issueNumbers.includes(i.number))
                        .map((issue) => (
                          <button
                            key={issue.number}
                            className="issue-picker-row"
                            onClick={() => choose(issue.number)}
                          >
                            <span className="picker-num">#{issue.number}</span>
                            <span className="picker-name">{issue.title}</span>
                          </button>
                        ))}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
