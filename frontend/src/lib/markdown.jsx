// Shared ReactMarkdown setup for every "agent reply" chat bubble in the app
// (ChatMessage.jsx for the user-facing TaskFlow Copilot, CopilotQueryBox.jsx
// for the admin "Ask the Copilot" box) -- one definition so a copilot
// response renders identically (and stays in sync) everywhere it appears.
//
// No @tailwindcss/typography plugin installed in this project, so markdown
// elements are styled directly via these `components`, not an uninstalled
// `prose` class. remark-gfm is required for table syntax (the LLMs this app
// talks to reach for markdown tables constantly for anything list-of-users
// or list-of-tasks shaped) -- react-markdown does not support tables out of
// the box without it.
export const MARKDOWN_COMPONENTS = {
  p: ({ children }) => <p className="my-1 first:mt-0 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="my-1 pl-4 list-disc space-y-0.5">{children}</ul>,
  ol: ({ children }) => <ol className="my-1 pl-4 list-decimal space-y-0.5">{children}</ol>,
  li: ({ children }) => <li>{children}</li>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  code: ({ children }) => <code className="px-1 py-0.5 rounded bg-black/10 dark:bg-white/10 text-[0.85em] font-mono">{children}</code>,
  a: ({ children, href }) => <a href={href} target="_blank" rel="noreferrer" className="underline underline-offset-2">{children}</a>,
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto rounded-lg border border-black/10 dark:border-white/10">
      <table className="w-full text-left text-[0.85em] border-collapse">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-black/5 dark:bg-white/10">{children}</thead>,
  tbody: ({ children }) => <tbody className="divide-y divide-black/10 dark:divide-white/10">{children}</tbody>,
  tr: ({ children }) => <tr>{children}</tr>,
  th: ({ children }) => <th className="px-2.5 py-1.5 font-semibold whitespace-nowrap">{children}</th>,
  td: ({ children }) => <td className="px-2.5 py-1.5 align-top">{children}</td>,
};
