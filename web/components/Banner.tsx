export function Banner({ disclaimer }: { disclaimer: string }) {
  return (
    <div role="note" className="border-b border-[#6a4b22] bg-[#2a2116]">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 px-5 py-3 text-sm text-[#f0d7b0] sm:flex-row sm:items-start sm:gap-4">
        <span className="w-fit shrink-0 rounded-full border border-accent px-2 py-0.5 text-[11px] uppercase tracking-[0.14em] text-accent">
          Sample
        </span>
        <p className="leading-relaxed">{disclaimer}</p>
      </div>
    </div>
  );
}
