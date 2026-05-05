'use client';

import { useState, KeyboardEvent, useEffect, useRef } from 'react';
import { QuestionEvent, UIState } from '../types';

interface ChatInputProps {
  onSend: (text: string, promptId?: string) => void;
  disabled: boolean;
  currentQuestion: QuestionEvent | null;
  uiState: UIState;
}

export function ChatInput({ onSend, disabled, currentQuestion, uiState }: ChatInputProps) {
  const [input, setInput] = useState("");
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (uiState === "awaiting_input") {
      inputRef.current?.focus();
    }
  }, [uiState, currentQuestion?.prompt_id]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim() && !disabled) {
      onSend(input.trim(), currentQuestion?.prompt_id);
      setInput("");
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const placeholder = currentQuestion
    ? "Write your answer..."
    : "Type your message...";

  return (
    <div className="space-y-3">
      {currentQuestion && (
        <div className="flex items-center gap-2 text-xs text-slate-300">
          <span className="inline-flex items-center rounded-full border border-slate-600 bg-slate-800 px-2.5 py-1">
            Awaiting your answer
          </span>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onSend("/skip", currentQuestion?.prompt_id)}
            className="rounded-full border border-slate-600 px-3 py-1 hover:bg-slate-800 disabled:opacity-50"
          >
            Skip
          </button>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onSend("/clarify", currentQuestion?.prompt_id)}
            className="rounded-full border border-indigo-500/50 px-3 py-1 text-indigo-200 hover:bg-indigo-500/10 disabled:opacity-50"
          >
            Clarify
          </button>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onSend("/cancel", currentQuestion?.prompt_id)}
            className="rounded-full border border-red-500/50 px-3 py-1 text-red-200 hover:bg-red-500/10 disabled:opacity-50"
          >
            Cancel
          </button>
        </div>
      )}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
          className="flex-1 rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
          style={{ minHeight: "44px", maxHeight: "120px" }}
        />
        <button
          type="submit"
          disabled={disabled || !input.trim()}
          className="rounded-xl bg-indigo-500 px-6 py-2 font-medium text-white hover:bg-indigo-400 disabled:cursor-not-allowed disabled:bg-slate-700"
        >
          {disabled ? "Sending..." : "Send"}
        </button>
      </form>
    </div>
  );
}
