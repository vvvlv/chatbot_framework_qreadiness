import { CollectedDataSection } from "../types";

const SECTION_HEADING = "## 5. COLLECTED ASSESSMENT DATA";

export function reportIncludesCollectedData(reportText: string): boolean {
  return reportText.includes(SECTION_HEADING);
}

export function parseCollectedDataFromReport(reportText: string): CollectedDataSection[] {
  const markerIndex = reportText.indexOf(SECTION_HEADING);
  if (markerIndex === -1) {
    return [];
  }

  const appendix = reportText.slice(markerIndex + SECTION_HEADING.length);
  const sections: CollectedDataSection[] = [];
  const chunks = appendix.split(/^### /m).slice(1);

  for (const chunk of chunks) {
    const newlineIndex = chunk.indexOf("\n");
    if (newlineIndex === -1) {
      continue;
    }
    const title = chunk.slice(0, newlineIndex).trim();
    const content = chunk
      .slice(newlineIndex + 1)
      .replace(/^---[\s\S]*$/m, "")
      .trim();
    if (title && content) {
      sections.push({ title, content });
    }
  }

  return sections;
}

export function resolveCollectedData(
  reportText: string,
  collectedData?: CollectedDataSection[]
): CollectedDataSection[] {
  if (collectedData && collectedData.length > 0) {
    return collectedData;
  }
  return parseCollectedDataFromReport(reportText);
}
