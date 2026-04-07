'use client';

import { useState, KeyboardEvent } from 'react';
import { QuestionEvent, UIState } from '../types';

interface ChatInputProps {
  onSend: (text: string) => void;
  disabled: boolean;
  currentQuestion: QuestionEvent | null;
  uiState: UIState;
}

export function ChatInput({ onSend, disabled, currentQuestion, uiState }: ChatInputProps) {
  const [input, setInput] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim() && !disabled) {
      onSend(input.trim());
      setInput("");
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  // Show question if awaiting input
  const displayText = currentQuestion ? currentQuestion.text : "";
  const placeholder = currentQuestion
    ? "Type your answer..."
    : "Type your message...";

  return (
    <div className="space-y-2">
      {currentQuestion && (
        <div className="p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
          <p className="text-sm font-medium text-blue-900 dark:text-blue-100 mb-1">
            Question:
          </p>
          <p className="text-sm text-blue-800 dark:text-blue-200">{displayText}</p>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              disabled={disabled}
              onClick={() => onSend("/skip")}
              className="px-3 py-1 text-xs text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded border border-gray-300 dark:border-gray-600 disabled:opacity-50"
            >
              Skip
            </button>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onSend("/clarify")}
              className="px-3 py-1 text-xs text-blue-700 dark:text-blue-200 hover:bg-blue-100 dark:hover:bg-blue-900/20 rounded border border-blue-300 dark:border-blue-700 disabled:opacity-50"
            >
              Clarify
            </button>
          </div>
        </div>
      )}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
          className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white resize-none"
          style={{ minHeight: "44px", maxHeight: "120px" }}
        />
        <button
          type="submit"
          disabled={disabled || !input.trim()}
          className="px-6 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
        >
          {disabled ? "Sending..." : "Send"}
        </button>
      </form>
    </div>
  );
}
