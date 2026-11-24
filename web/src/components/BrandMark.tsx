/** The TraceQ mark: lines of a document with a tick. Decorative; the name follows it. */
export function BrandMark({ className = "h-5 w-5 shrink-0 text-accent" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <rect x="1" y="1" width="22" height="22" rx="5" fill="currentColor" opacity="0.16" />
      <path d="M6 7h7M6 12h4M6 17h7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path
        d="M15 12l2 2 3.5-4"
        stroke="currentColor"
        strokeWidth="2"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
