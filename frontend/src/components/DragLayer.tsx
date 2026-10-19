import { useState, type RefObject } from "react";
import { createPortal } from "react-dom";
import { DragOverlay, useDndMonitor, type DragEndEvent, type DragOverEvent } from "@dnd-kit/core";
import type { IssueCard } from "../types/api";
import { CardGhost } from "./CardGhost";

/** The tracking column a drop would land in, or null: only tracking
 * columns take a drop, and not the one the card came from. */
export function landsIn(event: DragOverEvent | DragEndEvent): number | null {
  const target = event.over?.data.current;
  const source = event.active.data.current?.sourceColumnId;
  return target?.tracking && target.columnId !== source ? (target.columnId as number) : null;
}

/** Everything a drag changes on screen, kept out of the board's state:
 * the copy that follows the pointer, and the board's drop hints. Setting
 * board state here re-rendered every column and card when a drag started,
 * a visible stutter on picking a card up.
 *
 * The hints are attributes the stylesheet reads: `data-dragging` on the
 * board, `data-drag-source` on the column the card came from. React
 * doesn't manage either, so a column re-rendering mid-drag keeps them. */
export function DragLayer({ boardRef }: { boardRef: RefObject<HTMLElement | null> }) {
  const [dragging, setDragging] = useState<IssueCard | null>(null);
  // Off, the copy glides back to where it came from; on, it vanishes as
  // the card appears in its new column.
  const [lands, setLands] = useState(false);

  function hint(sourceColumnId: number | null) {
    const board = boardRef.current;
    if (!board) return;
    board.querySelectorAll("[data-drag-source]").forEach((el) => el.removeAttribute("data-drag-source"));
    if (sourceColumnId === null) {
      board.removeAttribute("data-dragging");
      return;
    }
    board.setAttribute("data-dragging", "");
    board.querySelector(`[data-column-id="${sourceColumnId}"]`)?.setAttribute("data-drag-source", "");
  }

  function finish() {
    setDragging(null);
    hint(null);
  }

  useDndMonitor({
    onDragStart(event) {
      setDragging((event.active.data.current?.issue as IssueCard | undefined) ?? null);
      setLands(false);
      hint((event.active.data.current?.sourceColumnId as number | undefined) ?? null);
    },
    onDragOver(event) {
      setLands(landsIn(event) !== null);
    },
    onDragEnd: finish,
    onDragCancel: finish,
  });

  // In the body, clear of every column's scroll box and transform.
  return createPortal(
    <DragOverlay dropAnimation={lands ? null : undefined}>{dragging && <CardGhost issue={dragging} />}</DragOverlay>,
    document.body
  );
}
