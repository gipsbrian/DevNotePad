import { useEffect, useState } from "react";

const ADVANCE_MS = 6000;

/** Miniatures of the real thing rather than screenshots: no binary
 * assets to keep current, and they theme with the rest of the app. */
const SLIDES = [
  {
    key: "columns",
    title: "Columns are saved filters",
    body: "Each column is a label, state, milestone or assignee that already exists on the repo.",
    art: (
      <div className="mock-board">
        {[
          { name: "Triage", accent: "var(--accent)", cards: 3 },
          { name: "In progress", accent: "var(--success)", cards: 2 },
          { name: "Blocked", accent: "var(--warn)", cards: 1 },
        ].map((col) => (
          <div className="mock-col" key={col.name}>
            <div className="mock-col-head">
              <span className="mock-dot" style={{ background: col.accent }} />
              {col.name}
            </div>
            {Array.from({ length: col.cards }).map((_, i) => (
              <div className="mock-card" key={i}>
                <span className="mock-line" />
                <span className="mock-line short" />
                <span className="mock-chip" style={{ background: col.accent }} />
              </div>
            ))}
          </div>
        ))}
        <div className="mock-flyer" aria-hidden />
      </div>
    ),
  },
  {
    key: "sticky",
    title: "Sticky notes that follow the board",
    body: "A scratch pad floating above the columns. Markdown, tickable checklists, dictation.",
    art: (
      <div className="mock-sticky">
        <div className="mock-sticky-head">Sticky notes</div>
        <div className="mock-sticky-paper">
          <span className="mock-sticky-date">Today</span>
          {["Ask about the rate-limit fix", "Write the residual risk section", "Ship the client summary"].map(
            (line, i) => (
              <div className="mock-task" key={line} style={{ ["--d" as string]: `${i * 0.9}s` }}>
                <span className="mock-box" />
                <span>{line}</span>
              </div>
            )
          )}
        </div>
      </div>
    ),
  },
  {
    key: "notes",
    title: "Private notes, shared when you say so",
    body: "Notes stay local until you push one — then it becomes a real comment on the issue.",
    art: (
      <div className="mock-note-flow">
        <div className="mock-note">
          <span className="mock-note-tag">Local note</span>
          <span className="mock-line" />
          <span className="mock-line short" />
        </div>
        <div className="mock-arrow" aria-hidden>
          →
        </div>
        <div className="mock-comment">
          <span className="mock-avatar" />
          <div>
            <span className="mock-line" />
            <span className="mock-line short" />
          </div>
        </div>
      </div>
    ),
  },
  {
    key: "insights",
    title: "See where the work went",
    body: "Opened against closed by week, across one person or the whole organisation.",
    art: (
      <div className="mock-chart">
        {[38, 62, 45, 80, 56, 72].map((h, i) => (
          <div className="mock-bar-pair" key={i} style={{ ["--d" as string]: `${i * 0.08}s` }}>
            <span className="mock-bar opened" style={{ ["--h" as string]: `${h}%` }} />
            <span className="mock-bar closed" style={{ ["--h" as string]: `${Math.max(18, h - 22)}%` }} />
          </div>
        ))}
      </div>
    ),
  },
];

export function ShowcaseSlides() {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (paused) return;
    const t = setTimeout(() => setIndex((i) => (i + 1) % SLIDES.length), ADVANCE_MS);
    return () => clearTimeout(t);
  }, [index, paused]);

  const slide = SLIDES[index];

  return (
    <aside
      className="login-showcase"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      aria-label="What DevNotePad does"
    >
      <div className="showcase-stage" key={slide.key}>
        {slide.art}
      </div>

      <div className="showcase-copy" key={`${slide.key}-copy`}>
        <h2>{slide.title}</h2>
        <p>{slide.body}</p>
      </div>

      <div className="showcase-dots" role="tablist" aria-label="Choose a slide">
        {SLIDES.map((s, i) => (
          <button
            key={s.key}
            role="tab"
            aria-selected={i === index}
            aria-label={s.title}
            className={`showcase-dot${i === index ? " on" : ""}`}
            onClick={() => setIndex(i)}
          />
        ))}
      </div>
    </aside>
  );
}
