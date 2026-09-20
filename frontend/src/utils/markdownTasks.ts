/** Toggling `- [ ]` / `- [x]` in raw markdown.
 *
 * react-markdown renders GFM task lists as disabled checkboxes, so making
 * them clickable means editing the source: find the Nth task line in
 * document order (which is the order they render in) and flip it. */

const TASK_LINE = /^(\s*(?:[-*+]|\d+[.)])\s+\[)([ xX])(\])/;

export function toggleTask(markdown: string, index: number): string {
  let seen = -1;
  return markdown
    .split("\n")
    .map((line) => {
      const m = line.match(TASK_LINE);
      if (!m) return line;
      seen += 1;
      if (seen !== index) return line;
      const next = m[2] === " " ? "x" : " ";
      return line.replace(TASK_LINE, `$1${next}$3`);
    })
    .join("\n");
}

export function taskProgress(markdown: string): { done: number; total: number } {
  let done = 0;
  let total = 0;
  for (const line of markdown.split("\n")) {
    const m = line.match(TASK_LINE);
    if (!m) continue;
    total += 1;
    if (m[2] !== " ") done += 1;
  }
  return { done, total };
}
