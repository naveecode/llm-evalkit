import Link from "next/link";

export function Header() {
  return (
    <header className="border-b border-line">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-4">
        <Link href="/" className="text-base font-medium tracking-tight text-paper">
          evalkit
        </Link>
        <nav className="flex items-center gap-5 text-sm text-muted">
          <Link href="/" className="hover:text-paper">
            Leaderboard
          </Link>
          <a
            href="https://github.com/naveecode/llm-evalkit"
            className="hover:text-paper"
            rel="noreferrer"
            target="_blank"
          >
            Source
          </a>
        </nav>
      </div>
    </header>
  );
}
