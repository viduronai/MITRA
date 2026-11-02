/** Renders `text` with the last occurrence of `accent` in Instrument Serif italic. */
export function Accented({ text, accent }: { text: string; accent?: string }) {
  const at = accent ? text.lastIndexOf(accent) : -1;
  if (!accent || at < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, at)}
      <em className="accent">{accent}</em>
      {text.slice(at + accent.length)}
    </>
  );
}

export const cssVars = (vars: Record<string, string | number>) => vars as React.CSSProperties;

/** Index of the last line containing the accent word (only that one gets it). */
export function accentLine(lines: string[], accent?: string): number {
  if (!accent) return -1;
  for (let i = lines.length - 1; i >= 0; i--) if (lines[i].includes(accent)) return i;
  return -1;
}
