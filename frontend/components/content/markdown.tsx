import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * A small, safe Markdown renderer for authored lesson text.
 *
 * It builds React elements directly and never uses `dangerouslySetInnerHTML`, so
 * lesson text (which can originate from uploaded or generated content and must be
 * treated as untrusted) cannot inject markup. Supported: headings, paragraphs,
 * bullet and numbered lists, block quotes, fenced code, rules, and inline code,
 * bold, italic and http(s) links. Anything else renders as plain text.
 */

type Block =
  | { type: "heading"; level: 1 | 2 | 3 | 4; text: string }
  | { type: "paragraph"; text: string }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "quote"; text: string }
  | { type: "code"; language: string; code: string }
  | { type: "rule" };

export function parseMarkdown(source: string): Block[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.trim() === "") {
      i++;
      continue;
    }

    const fence = line.match(/^```(\w*)\s*$/);
    if (fence) {
      const code: string[] = [];
      i++;
      while (i < lines.length && !/^```\s*$/.test(lines[i])) code.push(lines[i++]);
      i++; // closing fence
      blocks.push({ type: "code", language: fence[1], code: code.join("\n") });
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      blocks.push({ type: "heading", level: heading[1].length as 1 | 2 | 3 | 4, text: heading[2].trim() });
      i++;
      continue;
    }

    if (/^(-{3,}|\*{3,})\s*$/.test(line)) {
      blocks.push({ type: "rule" });
      i++;
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quote: string[] = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) quote.push(lines[i++].replace(/^>\s?/, ""));
      blocks.push({ type: "quote", text: quote.join(" ") });
      continue;
    }

    const bullet = /^\s*[-*]\s+/;
    const numbered = /^\s*\d+[.)]\s+/;
    if (bullet.test(line) || numbered.test(line)) {
      const ordered = numbered.test(line);
      const marker = ordered ? numbered : bullet;
      const items: string[] = [];
      while (i < lines.length && marker.test(lines[i])) items.push(lines[i++].replace(marker, ""));
      blocks.push({ type: "list", ordered, items });
      continue;
    }

    const paragraph: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^(#{1,4}\s|```|>\s?|\s*[-*]\s+|\s*\d+[.)]\s+)/.test(lines[i])
    ) {
      paragraph.push(lines[i++].trim());
    }
    blocks.push({ type: "paragraph", text: paragraph.join(" ") });
  }
  return blocks;
}

/** Inline formatting: `code`, **bold**, *italic*, [label](https://url). */
function renderInline(text: string, keyPrefix: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  const pattern = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\s][^*]*\*)|(\[[^\]]+\]\((https?:\/\/[^\s)]+)\))/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let n = 0;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const key = `${keyPrefix}-${n++}`;
    const token = match[0];
    if (match[1]) {
      nodes.push(
        <code key={key} className="rounded bg-surface px-1.5 py-0.5 font-mono text-[0.85em] text-fg">
          {token.slice(1, -1)}
        </code>
      );
    } else if (match[2]) {
      nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else if (match[3]) {
      nodes.push(<em key={key}>{token.slice(1, -1)}</em>);
    } else if (match[4]) {
      const label = token.slice(1, token.indexOf("]"));
      nodes.push(
        <a key={key} href={match[5]} target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-2">
          {label}
        </a>
      );
    }
    last = match.index + token.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

const HEADING_CLASS: Record<number, string> = {
  1: "mt-8 mb-3 text-2xl font-semibold tracking-tight text-fg",
  2: "mt-8 mb-3 text-xl font-semibold tracking-tight text-fg",
  3: "mt-6 mb-2 text-lg font-semibold text-fg",
  4: "mt-5 mb-2 text-base font-semibold text-fg",
};

export function Markdown({ source, className }: { source: string; className?: string }) {
  const blocks = React.useMemo(() => parseMarkdown(source), [source]);

  return (
    <div className={cn("text-[15px] leading-7 text-fg", className)}>
      {blocks.map((block, index) => {
        const key = `b${index}`;
        switch (block.type) {
          case "heading": {
            const Tag = `h${block.level}` as "h1" | "h2" | "h3" | "h4";
            return (
              <Tag key={key} className={HEADING_CLASS[block.level]}>
                {renderInline(block.text, key)}
              </Tag>
            );
          }
          case "paragraph":
            return (
              <p key={key} className="my-3">
                {renderInline(block.text, key)}
              </p>
            );
          case "list": {
            const List = block.ordered ? "ol" : "ul";
            return (
              <List key={key} className={cn("my-3 space-y-1.5 pl-6", block.ordered ? "list-decimal" : "list-disc")}>
                {block.items.map((item, itemIndex) => (
                  <li key={`${key}-${itemIndex}`}>{renderInline(item, `${key}-${itemIndex}`)}</li>
                ))}
              </List>
            );
          }
          case "quote":
            return (
              <blockquote key={key} className="my-4 border-l-2 border-primary-border pl-4 text-fg-muted">
                {renderInline(block.text, key)}
              </blockquote>
            );
          case "code":
            return (
              <pre
                key={key}
                className="my-4 overflow-x-auto rounded-lg border border-border bg-surface p-4 font-mono text-[13px] leading-6"
                tabIndex={0}
                aria-label={block.language ? `${block.language} code` : "Code"}
              >
                <code>{block.code}</code>
              </pre>
            );
          case "rule":
            return <hr key={key} className="my-6 border-border" />;
        }
      })}
    </div>
  );
}
