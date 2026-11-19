import { Link } from "react-router-dom";
import { ArrowLeft, Compass, LayoutDashboard } from "lucide-react";
import { useDocumentTitle } from "../lib/hooks";
import { Card } from "../components/ui";

export function NotFoundPage() {
  useDocumentTitle("Page not found");
  return (
    <div className="grid min-h-[60vh] place-items-center">
      <Card className="w-full max-w-xl p-8 text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-emerald-500/25 bg-emerald-500/10 text-emerald-400">
          <Compass className="h-6 w-6" />
        </div>
        <p className="mt-5 text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-600">
          Error 404
        </p>
        <h1 className="mt-2 text-2xl font-bold tracking-tight text-white">This page is off the chart</h1>
        <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-slate-500">
          The route does not exist in the Money Machine workspace. It may have been moved
          or the link is incomplete.
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
          <Link
            to="/"
            className="inline-flex h-10 items-center gap-2 rounded-xl bg-emerald-400 px-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300"
          >
            <LayoutDashboard className="h-4 w-4" /> Back to overview
          </Link>
          <button
            type="button"
            onClick={() => window.history.back()}
            className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-800 px-4 text-sm font-semibold text-slate-300 transition hover:border-slate-700 hover:text-white"
          >
            <ArrowLeft className="h-4 w-4" /> Go back
          </button>
        </div>
      </Card>
    </div>
  );
}
