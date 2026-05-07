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
            ? "bg-teal text-white"
            : "bg-skyblue/50 border border-skyblue text-navy"
        } ${isStreaming ? "opacity-70" : ""}`}
      >
        <span
          // className="prose prose-sm prose-headings:font-title prose-p:font-paragraph prose-a:font-paragraph"
          dangerouslySetInnerHTML={{ __html: marked(message.content) }}
        />
        {isStreaming && (
          <span className="inline-block w-2 h-2 bg-current rounded-full animate-pulse ml-1" />
        )}
      </div>
    </div>
  );
}
