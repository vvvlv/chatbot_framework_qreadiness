'use client';

import { useMemo } from 'react';
import { Message } from '../types';
import { marked } from 'marked';

interface MessageBubbleProps {
  message: Message;
  isStreaming?: boolean;
}

export function MessageBubble({ message, isStreaming }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const assistantHtml = useMemo(
    () => marked.parse(message.content, { async: false }),
    [message.content]
  );

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[90%] xs:max-w-[86%] md:max-w-[82%] h-max rounded-2xl px-3 xs:px-4 py-2.5 xs:py-3 shadow-sm ${
          isUser
            ? "bg-teal text-white"
            : "bg-beige text-teal"
        } ${isStreaming ? "opacity-70" : ""}`}
      >
        {isUser ?
        (<span className="md:text-md text-sm leading-relaxed">
          {message.content}
        </span>)
        : (<span
          className="prose md:prose-base prose-sm prose-teal leading-relaxed"
          dangerouslySetInnerHTML={{ __html: assistantHtml }}
        />)
        }
        {isStreaming && (
          <span className="inline-block w-2 h-2 bg-current rounded-full animate-pulse ml-1" />
        )}
      </div>
    </div>
  );
}
