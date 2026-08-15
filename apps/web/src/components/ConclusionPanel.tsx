import type { Conclusion } from "@veriframe/core";

/**
 * The plain-language summary, shown first because it is what most readers will
 * actually read. Everything below it on the report is the supporting detail.
 */
export function ConclusionPanel({ conclusion }: { conclusion: Conclusion }) {
  const { faces_analyzed: analyzed, faces_elevated: elevated } = conclusion;

  return (
    <section className="rounded-lg border-2 border-slate-900 bg-white p-6">
      <h2 className="text-xl font-semibold text-slate-900">{conclusion.headline}</h2>

      {analyzed > 0 && (
        <p className="mt-1 text-sm text-slate-500">
          {analyzed} {analyzed === 1 ? "face" : "faces"} analysed
          {elevated > 0 && ` · ${elevated} above the review threshold`}
        </p>
      )}

      <p className="mt-4 leading-relaxed text-slate-800">{conclusion.detail}</p>

      <div className="mt-4 rounded border-l-4 border-slate-900 bg-slate-50 px-4 py-3">
        <p className="text-sm font-medium text-slate-900">What to do next</p>
        <p className="mt-1 text-sm leading-relaxed text-slate-700">
          {conclusion.next_steps}
        </p>
      </div>
    </section>
  );
}
