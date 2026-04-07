'use client';

import { useChat } from '../hooks/useChat';
import { MessageBubble } from './MessageBubble';
import { ToolChrome } from './ToolChrome';
import { ChatInput } from './ChatInput';
import { useState, useEffect } from 'react';

export function ChatWindow() {
  const isUuid = (value: string): boolean => {
    return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
      value
    );
  };

  const [sessionId] = useState(() => {
    // Generate or retrieve session ID
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('session_id');
      if (stored && isUuid(stored)) return stored;
      const newId = crypto.randomUUID();
      localStorage.setItem('session_id', newId);
      return newId;
    }
    return crypto.randomUUID();
  });

  const {
    uiState,
    messages,
    toolMeta,
    currentQuestion,
    error,
    currentResponse,
    send,
    cancel,
  } = useChat(sessionId);

  return (
    <div className="flex flex-col h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <header className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-4">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Quantum Readiness Chatbot
        </h1>
        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
          Assess your company's quantum readiness through a structured conversational workflow
        </p>
      </header>

      {/* Tool Chrome */}
      {toolMeta && uiState !== "idle" && (
        <ToolChrome
          toolMeta={toolMeta}
          onCancel={cancel}
          visible={uiState === "tool_active" || uiState === "awaiting_input"}
        />
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="h-full flex items-center justify-center">
            <div className="text-center max-w-md">
              <p className="text-lg text-gray-700 dark:text-gray-300 font-medium">
                Choose an app to start
              </p>
              <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                Start the structured workflow without typing a command.
              </p>
              <button
                type="button"
                disabled={uiState === "streaming"}
                onClick={() => send("assessment")}
                className="mt-6 w-full px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
              >
                Start Quantum Readiness Assessment
              </button>
            </div>
          </div>
        )}

        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}

        {/* Streaming response */}
        {currentResponse && (
          <MessageBubble
            message={{
              id: "streaming",
              role: "assistant",
              content: currentResponse,
              timestamp: new Date(),
            }}
            isStreaming={true}
          />
        )}

        {/* Error message */}
        {error && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
            <p className="text-red-800 dark:text-red-200">{error}</p>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-6 py-4">
        <ChatInput
          onSend={send}
          disabled={uiState === "streaming"}
          currentQuestion={currentQuestion}
          uiState={uiState}
        />
      </div>
    </div>
  );
}
