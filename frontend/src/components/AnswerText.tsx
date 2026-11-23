import type { ReactNode } from "react";

const CANDIDATE = /([A-Za-z0-9]+(?:[-./][A-Za-z0-9]+)*)/g;

/** Wraps part numbers / error codes (tokens with letters AND digits, e.g. E42, 6ES7, 214-1AG40) in mono tags. */
export function renderCodes(text: string): ReactNode[] {
  return text.split(CANDIDATE).map((part, i) =>
    i % 2 === 1 && /\d/.test(part) && /[A-Za-z]/.test(part) ? (
      <code key={i} className="code-tag">
        {part}
      </code>
    ) : (
      part
    ),
  );
}

/**
 * Renders the small subset of Markdown the LLM uses (paragraphs, bullet/numbered
 * lists, **bold**), turns citation markers like [1] into clickable chips and
 * highlights part numbers / error codes.
 */
export function AnswerText({
  text,
  onCite,
  canCite,
  activeIndex,
}: {
  text: string;
  onCite: (n: number) => void;
  canCite: (n: number) => boolean;
  activeIndex?: number | null;
}) {
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  const ctx = { onCite, canCite, activeIndex };

  const flush = () => {
    if (!list) return;
    const items = list.items.map((it, i) => (
      <li key={i} className="pl-1 marker:text-amber-400/70">
        {inline(it, ctx)}
      </li>
    ));
    blocks.push(
      list.ordered ? (
        <ol key={blocks.length} className="list-decimal space-y-1.5 pl-5">{items}</ol>
      ) : (
        <ul key={blocks.length} className="list-disc space-y-1.5 pl-5">{items}</ul>
      ),
    );
    list = null;
  };

  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[*-]\s+(.*)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (bullet || numbered) {
      const ordered = Boolean(numbered);
      if (list && list.ordered !== ordered) flush();
      list ??= { ordered, items: [] };
      list.items.push((bullet ?? numbered)![1]);
    } else {
      flush();
      if (line.trim()) blocks.push(<p key={blocks.length}>{inline(line, ctx)}</p>);
    }
  }
  flush();
  return <div className="space-y-2.5 leading-relaxed">{blocks}</div>;
}

type Ctx = { onCite: (n: number) => void; canCite: (n: number) => boolean; activeIndex?: number | null };

function inline(text: string, { onCite, canCite, activeIndex }: Ctx): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|\[\d+\])/g).map((part, i) => {
    const cite = part.match(/^\[(\d+)\]$/);
    if (cite) {
      const n = Number(cite[1]);
      return canCite(n) ? (
        <button
          key={i}
          onClick={() => onCite(n)}
          aria-label={`Source ${n}`}
          className={`mx-0.5 inline-flex h-[18px] min-w-[18px] -translate-y-px items-center justify-center rounded-md px-1 align-middle text-[10.5px] font-bold transition ${
            activeIndex === n
              ? "bg-amber-400 text-ink-950 shadow-[0_0_12px_rgb(251_191_36/0.6)]"
              : "bg-amber-400/15 text-amber-300 ring-1 ring-amber-400/30 hover:bg-amber-400/30"
          }`}
        >
          {n}
        </button>
      ) : (
        <span key={i} className="text-ink-500">{part}</span>
      );
    }
    if (part.startsWith("**") && part.endsWith("**"))
      return (
        <strong key={i} className="font-semibold text-white">
          {renderCodes(part.slice(2, -2))}
        </strong>
      );
    return <span key={i}>{renderCodes(part)}</span>;
  });
}
