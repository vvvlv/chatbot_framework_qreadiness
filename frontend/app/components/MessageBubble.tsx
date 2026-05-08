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
            : "bg-beige border border-dark-beige text-teal"
        } ${isStreaming ? "opacity-70" : ""}`}
      >
        {isUser ?
        (<span>
          {message.content}
        </span>)
        : (<span
          className="prose prose-sm prose-teal"
          dangerouslySetInnerHTML={{ __html: marked(message.content) }}
        />)
        }
        {isStreaming && (
          <span className="inline-block w-2 h-2 bg-current rounded-full animate-pulse ml-1" />
        )}
      </div>
    </div>
  );
}
