// All calls go to the FastAPI backend. No AI keys ever reach the browser.
export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface SourceRef {
  chunk_id: string; university_name: string; category_code: string;
  source_pdf: string; source_page: number; original_source_pages?: string | null; excerpt: string;
}
export interface FollowUp { label: string; question: string }
export interface ChatReply {
  session_id: string; answer: string; sources: SourceRef[]; follow_ups: FollowUp[];
  needs_counsellor: boolean; missing_information: string[]; intent_category?: string | null;
}
export interface University { university_id: string; university_name: string }

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API}${path}`, { headers: { "Content-Type": "application/json" }, ...init });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Request failed (${r.status})`);
  return r.json();
}

export const listUniversities = () => req<{ universities: University[] }>("/api/universities");
export const createSession = (university_id?: string) =>
  req<{ id: string }>("/api/chat/sessions", { method: "POST", body: JSON.stringify({ university_id: university_id || null }) });
export const sendMessage = (session_id: string, message: string, university_id?: string) =>
  req<ChatReply>("/api/chat/messages", { method: "POST", body: JSON.stringify({ session_id, message, university_id: university_id || null }) });
export const sendFeedback = (session_id: string, helpful: boolean) =>
  req("/api/chat/feedback", { method: "POST", body: JSON.stringify({ session_id, helpful }) });

// Admin calls include the admin key from sessionStorage (set on the admin page).
export const adminReq = <T,>(path: string, init?: RequestInit) =>
  req<T>(path, { ...init, headers: { "Content-Type": "application/json", "x-admin-key": sessionStorage.getItem("randyll_admin_key") || "", ...(init?.headers || {}) } });
