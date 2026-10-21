"use client";
import { useState } from "react";
import { adminReq, API } from "@/lib/api";

interface Doc { document_id: string; source_pdf: string; university_name?: string; category_code?: string;
  pages: number; chunk_count: number; status: string; needs_review: boolean; review_reasons: string[] }
interface Status { documents: Doc[]; chunk_count: number; indexed_points: number;
  retrieval_failures: { id: number; query: string; reason: string; created: string }[] }
interface Chunk { chunk_id: string; source_page: number; original_source_pages?: string; content: string; verification_status: string }

export default function Admin() {
  const [key, setKey] = useState(""); const [authed, setAuthed] = useState(false);
  const [status, setStatus] = useState<Status | null>(null); const [chunks, setChunks] = useState<Chunk[]>([]);
  const [msg, setMsg] = useState(""); const [dir, setDir] = useState("");

  async function load() {
    sessionStorage.setItem("randyll_admin_key", key);
    try { setStatus(await adminReq<Status>("/api/admin/knowledge/status")); setAuthed(true); setMsg(""); }
    catch { setMsg("Invalid admin key or server unreachable."); }
  }
  async function act(label: string, fn: () => Promise<unknown>) {
    try { await fn(); setMsg(`${label} done.`); setStatus(await adminReq<Status>("/api/admin/knowledge/status")); }
    catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
  }

  if (!authed) return (
    <div className="mx-auto max-w-md px-4 py-16">
      <h1 className="text-xl font-bold text-blue-900">Randyll Overseas — Knowledge Admin</h1>
      <p className="mt-1 text-sm text-slate-500">Enter the admin API key (backend <code>ADMIN_API_KEY</code>).</p>
      <form className="mt-4 flex gap-2" onSubmit={(e) => { e.preventDefault(); load(); }}>
        <input type="password" value={key} onChange={(e) => setKey(e.target.value)} className="min-w-0 flex-1 rounded-lg border px-3 py-2" placeholder="Admin key" />
        <button className="rounded-lg bg-blue-700 px-4 py-2 font-semibold text-white">Sign in</button>
      </form>
      {msg && <p role="alert" className="mt-2 text-sm text-red-600">{msg}</p>}
      <a href="/" className="mt-4 block text-sm text-blue-700 hover:underline">← Back to chat</a>
    </div>);

  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-blue-900">Knowledge Administration</h1>
        <a href="/" className="text-sm text-blue-700 hover:underline">← Chat</a>
      </div>
      {msg && <p className="mt-2 rounded-lg bg-blue-50 px-3 py-2 text-sm">{msg}</p>}
      <p className="mt-2 text-sm text-slate-600">{status?.chunk_count ?? 0} chunks · {status?.indexed_points ?? 0} indexed points. Only <b>approved</b> content is visible to students.</p>

      <div className="mt-4 flex flex-wrap gap-2">
        <input value={dir} onChange={(e) => setDir(e.target.value)} placeholder="Server directory of categorized PDFs (optional)"
          className="min-w-0 flex-1 rounded-lg border px-3 py-2 text-sm" />
        <button onClick={() => act("Ingest", () => adminReq("/api/admin/knowledge/ingest", { method: "POST", body: JSON.stringify({ directory: dir || null, approve: false }) }))}
          className="rounded-lg bg-blue-700 px-3 py-2 text-sm font-semibold text-white">Ingest (pending review)</button>
        <button onClick={() => act("Reindex", () => adminReq("/api/admin/knowledge/reindex", { method: "POST" }))}
          className="rounded-lg bg-slate-700 px-3 py-2 text-sm font-semibold text-white">Reindex approved</button>
        <label className="cursor-pointer rounded-lg bg-emerald-700 px-3 py-2 text-sm font-semibold text-white">
          Upload PDF
          <input type="file" accept="application/pdf" className="hidden" onChange={async (e) => {
            const f = e.target.files?.[0]; if (!f) return;
            const fd = new FormData(); fd.append("file", f);
            await act("Upload", async () => {
              const r = await fetch(`${API}/api/admin/knowledge/upload`, { method: "POST", body: fd,
                headers: { "x-admin-key": sessionStorage.getItem("randyll_admin_key") || "" } });
              if (!r.ok) throw new Error(`Upload failed (${r.status})`);
            });
          }} />
        </label>
      </div>

      <div className="mt-4 overflow-x-auto rounded-xl bg-white ring-1 ring-slate-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-slate-500"><tr>
            <th className="px-3 py-2">Document</th><th className="px-3 py-2">University</th><th className="px-3 py-2">Cat</th>
            <th className="px-3 py-2">Chunks</th><th className="px-3 py-2">Status</th><th className="px-3 py-2">Actions</th></tr></thead>
          <tbody>
            {status?.documents.map((d) => (
              <tr key={d.document_id} className="border-t">
                <td className="px-3 py-2">{d.source_pdf}{d.needs_review && <span className="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800" title={d.review_reasons.join("; ")}>needs review</span>}</td>
                <td className="px-3 py-2">{d.university_name ?? "—"}</td><td className="px-3 py-2">{d.category_code}</td>
                <td className="px-3 py-2">{d.chunk_count}</td><td className="px-3 py-2">{d.status}</td>
                <td className="px-3 py-2">
                  <span className="flex gap-2">
                    <button className="text-blue-700 hover:underline" onClick={() => adminReq<{ chunks: Chunk[] }>(`/api/admin/knowledge/documents/${d.document_id}/chunks`).then((r) => setChunks(r.chunks))}>Inspect vs source</button>
                    <button className="text-emerald-700 hover:underline" onClick={() => act("Approve", () => adminReq(`/api/admin/knowledge/documents/${d.document_id}/review`, { method: "POST", body: JSON.stringify({ status: "approved" }) }))}>Approve</button>
                    <button className="text-red-700 hover:underline" onClick={() => act("Reject", () => adminReq(`/api/admin/knowledge/documents/${d.document_id}/review`, { method: "POST", body: JSON.stringify({ status: "rejected" }) }))}>Reject</button>
                  </span>
                </td>
              </tr>))}
          </tbody>
        </table>
      </div>

      {chunks.length > 0 && (
        <section className="mt-4 rounded-xl bg-white p-4 ring-1 ring-slate-200">
          <h2 className="font-semibold">Extracted chunks — compare with the original PDF text</h2>
          <div className="mt-2 max-h-96 space-y-2 overflow-y-auto">
            {chunks.map((c) => (
              <article key={c.chunk_id} className="rounded-lg bg-slate-50 p-3 text-sm ring-1 ring-slate-200">
                <p className="text-xs text-slate-500">{c.chunk_id} · categorized p.{c.source_page} · original pp. {c.original_source_pages ?? "?"} · {c.verification_status}</p>
                <p className="mt-1 whitespace-pre-wrap">{c.content}</p>
              </article>))}
          </div>
        </section>)}

      {status && status.retrieval_failures.length > 0 && (
        <section className="mt-4 rounded-xl bg-white p-4 ring-1 ring-slate-200">
          <h2 className="font-semibold">Recent retrieval failures (questions the bot could not verify)</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600">
            {status.retrieval_failures.map((f) => <li key={f.id}>“{f.query}” — {f.reason}</li>)}
          </ul>
        </section>)}
    </div>);
}
