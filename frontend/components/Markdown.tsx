"use client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Clean, scannable rendering of assistant answers: bold headings, tidy
 *  bullets, bold figures, simple tables. */
export default function Markdown({ children }: { children: string }) {
  return (
    <div className="text-[15px] leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h2 className="mb-2 mt-1 text-lg font-bold text-slate-900">{children}</h2>,
          h2: ({ children }) => <h2 className="mb-2 mt-3 text-base font-bold text-slate-900 first:mt-0">{children}</h2>,
          h3: ({ children }) => <h3 className="mb-1.5 mt-3 text-[15px] font-bold text-slate-900 first:mt-0">{children}</h3>,
          h4: ({ children }) => <h4 className="mb-1 mt-2.5 font-bold text-slate-900 first:mt-0">{children}</h4>,
          p: ({ children }) => <p className="my-1.5 first:mt-0 last:mb-0">{children}</p>,
          ul: ({ children }) => <ul className="my-1.5 list-disc space-y-1 pl-5">{children}</ul>,
          ol: ({ children }) => <ol className="my-1.5 list-decimal space-y-1 pl-5">{children}</ol>,
          li: ({ children }) => <li className="marker:text-slate-400">{children}</li>,
          strong: ({ children }) => <strong className="font-bold text-slate-900">{children}</strong>,
          a: ({ children, href }) => <a href={href} className="font-medium text-blue-700 underline">{children}</a>,
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto">
              <table className="w-full border-collapse overflow-hidden rounded-lg text-sm ring-1 ring-slate-200">{children}</table>
            </div>),
          thead: ({ children }) => <thead className="bg-slate-200/70 text-left">{children}</thead>,
          th: ({ children }) => <th className="px-2.5 py-1.5 font-semibold">{children}</th>,
          td: ({ children }) => <td className="border-t border-slate-200 px-2.5 py-1.5">{children}</td>,
          blockquote: ({ children }) => <blockquote className="my-2 border-l-4 border-blue-300 pl-3 text-slate-600">{children}</blockquote>,
          code: ({ children }) => <code className="rounded bg-slate-200/80 px-1 py-0.5 text-[13px]">{children}</code>,
          hr: () => <hr className="my-3 border-slate-200" />,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
