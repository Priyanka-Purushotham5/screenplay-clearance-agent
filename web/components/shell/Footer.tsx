/** The quiet strip under everything that is not a run. */
export default function Footer() {
  return (
    <footer
      className="flex shrink-0 items-center gap-3 border-t border-slate-800
                 bg-slate-900 px-4 py-2 text-[11px] text-slate-500"
    >
      <span>Script to Clearance</span>
      <span aria-hidden>·</span>
      <span>Screenplay rights clearance, with sources</span>
      <span className="ml-auto">
        Findings are research, not legal advice.
      </span>
    </footer>
  );
}
