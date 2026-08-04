import { Bot, Sparkles } from 'lucide-react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';

export default function CopilotButton({ onClick, isOpen }) {
  return (
    <motion.button
      type="button"
      onClick={onClick}
      whileHover={{ scale: 1.03 }}
      whileTap={{ scale: 0.97 }}
      aria-expanded={isOpen}
      aria-label="Open AI Copilot"
      data-copilot-widget
      className={cn(
        'hidden sm:flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium text-white transition-shadow',
        'bg-gradient-to-r from-violet-600 via-indigo-600 to-purple-600',
        'shadow-md shadow-indigo-500/30 hover:shadow-lg hover:shadow-indigo-500/40'
      )}
    >
      <Bot className="w-4 h-4" />
      AI Copilot
      <Sparkles className="w-3.5 h-3.5 opacity-80" />
    </motion.button>
  );
}
