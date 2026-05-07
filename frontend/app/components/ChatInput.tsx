'use client';

import { useState, KeyboardEvent, useEffect, useRef } from 'react';
import { QuestionEvent, UIState } from '../types';

interface ChatInputProps {
  onSend: (text: string, promptId?: string) => void;
  onDelete: () => void;
  disabled: boolean;
  currentQuestion: QuestionEvent | null;
  uiState: UIState;
}

export function ChatInput({ onSend, onDelete, disabled, currentQuestion, uiState }: ChatInputProps) {
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
        <div className="flex items-center gap-2 text-xs font-paragraph">
          <span className="inline-flex items-center rounded-full text-navy bg-transparent px-2.5 py-1">
            Awaiting your answer...
          </span>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onSend("/skip", currentQuestion?.prompt_id)}
            className="rounded-full border border-navy px-3 py-1 text-navy hover:bg-navy/10 hover:cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Skip
          </button>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onSend("/clarify", currentQuestion?.prompt_id)}
            className="rounded-full border border-teal px-3 py-1 text-teal hover:bg-teal/10 hover:cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Clarify
          </button>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onSend("/cancel", currentQuestion?.prompt_id)}
            className="rounded-full border border-red-500 px-3 py-1 text-red-500 hover:bg-red-500/10 hover:cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
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
          className="flex-1 rounded-xl bg-white px-4 py-3 text-navy placeholder:text-navy/50 focus:outline-none focus:ring-2 focus:ring-navy resize-none"
          style={{ minHeight: "44px", maxHeight: "120px" }}
        />
        <button
          type="button"
          disabled={disabled}
          onClick={onDelete}
          className="rounded-xl bg-white border border-red-500 px-6 py-2 font-paragraph font-medium text-red-500 hover:bg-red-500/20 hover:cursor-pointer disabled:cursor-not-allowed disabled:border-slate-400 disabled:text-slate-400"
        >
          {"Clear"}
        </button>
        <button
          type="submit"
          disabled={disabled || !input.trim()}
          className="rounded-xl bg-navy px-6 py-2 font-paragraph font-medium text-white hover:bg-navy/80 hover:cursor-pointer disabled:cursor-not-allowed disabled:bg-slate-400"
        >
          {disabled ? "Sending..." : "Send"}
        </button>
      </form>
    </div>
  );
}
