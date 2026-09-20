import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Renders GitHub-flavored markdown (issue bodies, comments, notes).
 * Raw HTML embedded in the markdown is intentionally left un-rendered
 * (react-markdown's default, no rehype-raw) rather than executed. */
export function Markdown({ text }: { text: string }) {
  return (
    <div className="markdown-body">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}
