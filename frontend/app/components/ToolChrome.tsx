'use client';

import { ToolMeta } from '../types';

interface ToolChromeProps {
  toolMeta: ToolMeta | null;
  onCancel: () => void;
  visible: boolean;
}

export function ToolChrome({ toolMeta, onCancel, visible }: ToolChromeProps) {
  if (!visible) return null;

  if (!toolMeta) return null;

  const progress = toolMeta.total > 0 ? (toolMeta.step / toolMeta.total) * 100 : 0;

  return (
    <div className="px-6 py-3">
      <div className="flex items-center justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-sm font-medium text-indigo-900 dark:text-indigo-100">
              {toolMeta.name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
            </span>
            <span className="text-xs text-indigo-700 dark:text-indigo-300">
              Step {toolMeta.step} of {toolMeta.total}
            </span>
          </div>
          <div className="w-full bg-indigo-200 dark:bg-indigo-800 rounded-full h-2">
            <div
              className="bg-indigo-600 dark:bg-indigo-400 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
