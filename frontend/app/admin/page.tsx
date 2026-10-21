"use client";
import { useState } from "react";
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export default function Admin() {
  const [key, setKey] = useState(""); const [data, setData] = useState<any>(null); const [chunks, setChunks] = useState<any[]>([]); const [err, setErr] = useState("");
  const H = { "Content-Type": "application/json", "X-Admin-Key": key };
  async function load() { setErr(""); const r = await fetch(`${API}/api/admin/knowledge/status`, { headers: H }); if (!r.ok) return setErr("Unauthorized or backend unavailable"); setData(await r.json()); }
  async function review(id: string, status: string) { await fetch(`${API}/api/admin/knowledge/documents/${id}/review`, { method: "POST", headers: H, body: JSON.stringify({ status }) }); load(); }
  async function view(id: string) { const r = await fetch(`${API}/api/admin/knowledge/documents/${id}/chunks`, { headers: H }); setChunks((await r.json()).chunks || []); }
  async function act(path: string, body?: any) { const r = await fetch(`${API}${path}`, { method: "POST", headers: H, body: body ? JSON.stringify(body) : undefined }); if (!r.ok) setErr("Action failed"); load(); }
  return (<main className="mx-auto max-w-5xl p-6"><h1 className="text-2xl font-bold text-[#0b2a5b]">Knowledge Administration</h1>
    <div className="mt-4 flex gap-2"><input type="password" className="rounded border p-2" placeholder="Admin API key" value={key} onChange={e => setKey(e.target.value)} />
    <button className="rounded bg-[#0b2a5b] px-3 text-white" onClick={load}>Load status</button>
    <button className="rounded border px-3" onClick={() => act("/api/admin/knowledge/ingest", { directory: undefined, approve: false })}>Re-ingest</button>
    <button className="rounded border px-3" onClick={() => act("/api/admin/knowledge/reindex")}>Reindex</button></div>
    {err && <p className="mt-2 rounded bg-red-50 p-2 text-sm text-red-700">{err}</p>}
    {data && <p className="mt-3 text-sm">Documents: {data.documents.length} · Chunks: {data.chunk_count} · Indexed points: {data.indexed_points}</p>}
    <div className="mt-4 space-y-2">{(data?.documents || []).map((d: any) => (<div key={d.document_id} className="rounded border bg-white p-3 text-sm">
      <b>{d.university_name}</b> · {d.category_code} · {d.source_pdf} · chunks: {d.chunk_count} · <span className="font-semibold">{d.status}</span>{d.needs_review && <span className="text-red-600"> needs review: {d.review_reasons.join("; ")}</span>}
      <div className="mt-1 flex gap-1"><button className="rounded bg-green-600 px-2 text-white" onClick={() => review(d.document_id, "approved")}>Approve</button>
      <button className="rounded bg-red-600 px-2 text-white" onClick={() => review(d.document_id, "rejected")}>Reject</button>
      <button className="rounded border px-2" onClick={() => view(d.document_id)}>Inspect chunks (compare with PDF)</button></div></div>))}
    </div>
    {chunks.length > 0 && <section className="mt-4 rounded border bg-white p-3"><h2 className="font-semibold">Extracted chunks (source_page = page in categorized PDF)</h2>
      {chunks.map((c: any) => <details key={c.chunk_id} className="border-b py-2 text-sm"><summary>{c.category_code} · p.{c.source_page} · original pp.{c.original_source_pages} · {c.verification_status}</summary><pre className="whitespace-pre-wrap pt-2">{c.content}</pre></details>)}</section>}
    {data?.retrieval_failures?.length > 0 && <section className="mt-4 rounded border bg-amber-50 p-3 text-sm"><h2 className="font-semibold">Recent retrieval failures</h2>{data.retrieval_failures.map((f: any) => <p key={f.id}>{f.query} — {f.reason}</p>)}</section>}
  </main>);
}
