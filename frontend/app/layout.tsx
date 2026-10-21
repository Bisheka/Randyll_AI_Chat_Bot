import "./globals.css";
export const metadata = { title: "Randyll Overseas AI Counsellor" };
export default function Root({ children }: { children: React.ReactNode }) {
  return (<html lang="en"><body className="bg-slate-50 text-slate-900">
    <nav className="flex gap-4 bg-white px-4 py-2 text-sm shadow"><a className="font-bold text-[#0b2a5b]" href="/">Randyll Overseas</a><a href="/">Student Chat</a><a href="/admin">Admin</a></nav>
    {children}</body></html>);
}
