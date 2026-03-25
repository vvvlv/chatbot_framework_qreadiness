'use client';

import { ToolMeta } from '../types';

interface ToolChromeProps {
  toolMeta: ToolMeta;
  onCancel: () => void;
  visible: boolean;
}

export function ToolChrome({ toolMeta, onCancel, visible }: ToolChromeProps) {
  if (!visible) return null;

  const progress = toolMeta.total > 0 ? (toolMeta.step / toolMeta.total) * 100 : 0;

  return (
    <div className="bg-blue-50 dark:bg-blue-900/20 border-b border-blue-200 dark:border-blue-800 px-6 py-3">
      <div className="flex items-center justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-sm font-medium text-blue-900 dark:text-blue-100">
              {toolMeta.name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
            </span>
            <span className="text-xs text-blue-700 dark:text-blue-300">
              Step {toolMeta.step} of {toolMeta.total}
            </span>
          </div>
          <div className="w-full bg-blue-200 dark:bg-blue-800 rounded-full h-2">
            <div
              className="bg-blue-600 dark:bg-blue-400 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
        <button
          onClick={onCancel}
          className="ml-4 px-3 py-1 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded border border-red-300 dark:border-red-700"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
