export function Banner({
  disclaimer,
  tone = "sample",
}: {
  disclaimer: string;
  tone?: "sample" | "measured";
}) {
  const measured = tone === "measured";
  return (
    <div
      role="note"
      className={
        measured
          ? "border-b border-[#24523a] bg-[#14241c]"
          : "border-b border-[#6a4b22] bg-[#2a2116]"
      }
    >
      <div
        className={`mx-auto flex max-w-6xl flex-col gap-2 px-5 py-3 text-sm sm:flex-row sm:items-start sm:gap-4 ${
          measured ? "text-[#d5ecdf]" : "text-[#f0d7b0]"
        }`}
      >
        <span className="w-fit shrink-0 rounded-full border border-accent px-2 py-0.5 text-[11px] uppercase tracking-[0.14em] text-accent">
          {measured ? "Measured" : "Sample"}
        </span>
        <p className="leading-relaxed">{disclaimer}</p>
      </div>
    </div>
  );
}
