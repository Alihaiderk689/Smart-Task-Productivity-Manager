import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { MARKDOWN_COMPONENTS } from '@/lib/markdown';
import { cn } from '@/lib/utils';

export default function ChatMessage({ role, content }) {
  const isUser = role === 'user';

  return (
    <div className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[85%] px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed',
          isUser
            ? 'bg-indigo-600 text-white rounded-br-sm'
            : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 rounded-bl-sm'
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{content}</p>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>{content}</ReactMarkdown>
        )}
      </div>
    </div>
  );
}
