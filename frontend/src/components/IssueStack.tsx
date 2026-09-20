import { useEffect, useState } from "react";
import type { Column, IssueCard } from "../types/api";
import { IssueDetailModal } from "./IssueDetailModal";
import { IconChevronLeft, IconPlus, IconX } from "./Icons";

/** How many issues can sit side by side. Past three the panes are too
 * narrow for the description to be worth reading. */
export const MAX_OPEN_ISSUES = 3;

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

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      // Back out of the picker first — Escape closing the whole
      // comparison because a menu was open would be a rude surprise.
      if (picking) setPicking(false);
      else onCloseAll();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [picking, onCloseAll]);

  useEffect(() => {
    if (!picking) setPickedColumn(null);
  }, [picking]);

  const full = issueNumbers.length >= MAX_OPEN_ISSUES;

  function choose(issueNumber: number) {
    onAdd(issueNumber);
    setPicking(false);
  }

  return (
    <div className="modal-overlay" onClick={onCloseAll}>
      <div className={`issue-stack count-${issueNumbers.length}`}>
        {issueNumbers.map((number) => (
          <div className="issue-pane-wrap" key={number}>
            {issueNumbers.length > 1 && (
              <button
                className="pane-close"
                onClick={(e) => {
                  e.stopPropagation();
                  onCloseOne(number);
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
              onClose={() => onCloseOne(number)}
              onChanged={onChanged}
              canWrite={canWrite}
              writeBlockReason={writeBlockReason}
            />
          </div>
        ))}

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
