'use client';

import { Message } from '../types';
import { marked } from 'marked';

interface MessageBubbleProps {
  message: Message;
  isStreaming?: boolean;
}

export function MessageBubble({ message, isStreaming }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[82%] rounded-2xl px-4 py-3 shadow-sm ${
          isUser
            ? "bg-indigo-500 text-white"
            : "border border-slate-700/80 bg-slate-900/90 text-slate-100"
        } ${isStreaming ? "opacity-70" : ""}`}
      >
        <span
          className="prose prose-invert prose-sm max-w-none"
          dangerouslySetInnerHTML={{ __html: marked(message.content) }}
        />
        {isStreaming && (
          <span className="inline-block w-2 h-2 bg-current rounded-full animate-pulse ml-1" />
        )}
      </div>
    </div>
  );
}
