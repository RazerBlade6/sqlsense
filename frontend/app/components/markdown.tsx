import { Fragment, type ReactNode } from "react";

/** Renders the small Markdown subset the synthesizer writes: paragraphs, bullets, **bold**,
 *  `code`, and [n] citation markers. */
export function Markdown({ text, onCite }: { text: string; onCite?: (id: number) => void }) {
  const blocks: ReactNode[] = [];
  let bullets: string[] = [];

  const flush = () => {
    if (bullets.length) {
      blocks.push(
        <ul key={`ul-${blocks.length}`}>
          {bullets.map((item, i) => (
            <li key={i}>{inline(item, onCite)}</li>
          ))}
        </ul>,
      );
      bullets = [];
    }
  };

  for (const line of text.split("\n")) {
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
    if (bullet) {
      bullets.push(bullet[1]);
    } else {
      flush();
      if (line.trim()) blocks.push(<p key={`p-${blocks.length}`}>{inline(line, onCite)}</p>);
    }
  }
  flush();
  return <div className="markdown">{blocks}</div>;
}

function inline(text: string, onCite?: (id: number) => void): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`|\[\d+\])/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`")) return <code key={i}>{part.slice(1, -1)}</code>;
    const cite = part.match(/^\[(\d+)\]$/);
    if (cite) {
      const id = Number(cite[1]);
      return (
        <button key={i} type="button" className="citeMarker" onClick={() => onCite?.(id)}>
          {id}
        </button>
      );
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}
