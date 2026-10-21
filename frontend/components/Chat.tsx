"use client";
import { useEffect, useRef, useState } from "react";
import Markdown from "@/components/Markdown";
import { createSession, listUniversities, sendFeedback, sendMessage, type FollowUp, type SourceRef, type University } from "@/lib/api";

interface Msg { role: "user" | "assistant"; content: string; sources?: SourceRef[]; followUps?: FollowUp[]; needsCounsellor?: boolean }

const SUGGESTED = ["What are the language requirements (TOPIK/IELTS)?", "How much is the tuition?",
  "What scholarships are available?", "What documents do I need to apply?", "What is the application deadline?"];

export default function Chat() {
  const [msgs, setMsgs] = useState<Msg[]>([{ role: "assistant",
    content: "Welcome to Randyll Overseas! Ask me anything about Korean university admissions — fees, scholarships, language requirements, deadlines and more." }]);
  const [input, setInput] = useState(""); const [busy, setBusy] = useState(false);
  const [error, setError] = useState(""); const [session, setSession] = useState("");
  const [unis, setUnis] = useState<University[]>([]); const [uni, setUni] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, busy]);
  useEffect(() => { listUniversities().then((r) => setUnis(r.universities)).catch(() => setError("Cannot reach the counselling service. Please try again later.")); }, []);

  async function ensureSession(): Promise<string> {
    if (session) return session;
    const s = await createSession(uni || undefined); setSession(s.id); return s.id;
  }
  async function ask(text: string) {
    const q = text.trim(); if (!q || busy) return;
    setInput(""); setError(""); setBusy(true);
    setMsgs((m) => [...m, { role: "user", content: q }]);
    try {
      const sid = await ensureSession();
      const r = await sendMessage(sid, q, uni || undefined);
      setMsgs((m) => [...m, { role: "assistant", content: r.answer, sources: r.sources, followUps: r.follow_ups, needsCounsellor: r.needs_counsellor }]);
    } catch (e) { setError(e instanceof Error ? e.message : "Something went wrong."); }
    finally { setBusy(false); }
  }

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-3xl flex-col px-3 py-4 sm:px-6">
      <header className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-bold text-blue-900">Randyll Overseas</h1>
          <p className="text-sm text-slate-500">AI Student Counselling · Korean university admissions</p>
        </div>
        <a href="/admin" className="text-sm font-medium text-blue-700 hover:underline">Admin</a>
      </header>

      <label className="mb-3 flex items-center gap-2 text-sm">
        <span className="font-medium">University</span>
        <select value={uni} onChange={(e) => { setUni(e.target.value); setSession(""); }}
          className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-2 py-1.5 sm:flex-none">
          <option value="">Any / not sure yet</option>
          {unis.map((u) => <option key={u.university_id} value={u.university_id}>{u.university_name}</option>)}
        </select>
      </label>

      <main className="flex-1 space-y-3 overflow-y-auto rounded-2xl bg-white p-3 shadow-sm ring-1 ring-slate-200 sm:p-4" aria-live="polite">
        {msgs.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div className={m.role === "user"
              ? "max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-blue-700 px-3.5 py-2.5 text-white"
              : "max-w-[92%] rounded-2xl rounded-bl-sm bg-slate-100 px-3.5 py-2.5"}>
              {m.role === "assistant" ? <Markdown>{m.content}</Markdown> : m.content}
              {m.needsCounsellor && (
                <a href="mailto:info@randylloverseas.example" className="mt-2 inline-block rounded-lg bg-amber-500 px-3 py-1.5 text-sm font-semibold text-white">
                  Talk to a counsellor
                </a>)}
              {m.followUps && m.followUps.length > 0 && (
                <div className="mt-2.5 flex flex-wrap items-center gap-1.5 border-t border-slate-200 pt-2">
                  <span className="text-xs text-slate-500">You can also ask:</span>
                  {m.followUps.map((f) => (
                    <button key={f.label} onClick={() => ask(f.question)}
                      className="rounded-md bg-white px-2 py-1 text-xs text-blue-800 ring-1 ring-blue-200 hover:bg-blue-50">
                      {f.label}
                    </button>))}
                </div>)}
            </div>
          </div>
        ))}
        {busy && <p className="text-sm text-slate-500">Searching the university guidelines…</p>}
        <div ref={endRef} />
      </main>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {SUGGESTED.map((s) => (
          <button key={s} onClick={() => ask(uni ? `${s} (${unis.find((u) => u.university_id === uni)?.university_name ?? ""})` : s)}
            className="rounded-full bg-white px-3 py-1.5 text-xs ring-1 ring-slate-300 hover:bg-blue-50">{s}</button>))}
      </div>

      {error && <p role="alert" className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

      <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); ask(input); }}>
        <input value={input} onChange={(e) => setInput(e.target.value)} maxLength={4000}
          placeholder="Ask about fees, TOPIK, scholarships, deadlines…" aria-label="Your question"
          className="min-w-0 flex-1 rounded-xl border border-slate-300 bg-white px-3 py-2.5" />
        <button disabled={busy || !input.trim()} className="rounded-xl bg-blue-700 px-4 py-2.5 font-semibold text-white disabled:opacity-40">Send</button>
      </form>

      {session && (
        <div className="mt-2 flex items-center gap-3 text-xs text-slate-500">
          <span>Was this helpful?</span>
          <button onClick={() => sendFeedback(session, true).catch(() => {})} className="hover:underline">Yes</button>
          <button onClick={() => sendFeedback(session, false).catch(() => {})} className="hover:underline">No</button>
          <span className="ml-auto">Guideline information only — admission, visa and scholarship outcomes are never guaranteed.</span>
        </div>)}
    </div>
  );
}
