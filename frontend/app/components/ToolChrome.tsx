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
    <div className="flex-1 px-2 py-2">
      <div className="flex items-center justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-paragraph text-navy">
              Step {toolMeta.step} of {toolMeta.total}
            </span>
          </div>
          <div className="w-full bg-navy/50 rounded-full h-2">
            <div
              className="bg-navy h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
