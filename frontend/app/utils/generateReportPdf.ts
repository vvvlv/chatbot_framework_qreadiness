import { jsPDF } from "jspdf";
import { CollectedDataSection } from "../types";
import { reportIncludesCollectedData } from "./reportCollectedData";

const MARGIN = 18;
const LINE_HEIGHT = 5.5;
const TITLE_SIZE = 16;
const HEADING_SIZE = 12;
const BODY_SIZE = 10;
const SMALL_SIZE = 9;

function sanitizeFilename(name: string): string {
  const cleaned = name
    .replace(/[^\w\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .toLowerCase();
  return cleaned || "quantum-readiness-report";
}

function markdownToPlainText(markdown: string): string {
  return markdown
    .replace(/\r\n/g, "\n")
    .replace(/^---\s*$/gm, "")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/\*(.*?)\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/^\s*[-*]\s+/gm, "• ")
    .replace(/[📈⚠️•]/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function ensurePageSpace(doc: jsPDF, y: number, needed: number): number {
  const pageHeight = doc.internal.pageSize.getHeight();
  if (y + needed > pageHeight - MARGIN) {
    doc.addPage();
    return MARGIN;
  }
  return y;
}

function writeWrappedText(
  doc: jsPDF,
  text: string,
  x: number,
  y: number,
  maxWidth: number,
  fontSize: number,
  style: "normal" | "bold" = "normal"
): number {
  doc.setFont("helvetica", style);
  doc.setFontSize(fontSize);
  const lines = doc.splitTextToSize(text, maxWidth) as string[];
  for (const line of lines) {
    y = ensurePageSpace(doc, y, LINE_HEIGHT);
    doc.text(line, x, y);
    y += LINE_HEIGHT;
  }
  return y;
}

function writeSectionHeading(doc: jsPDF, text: string, x: number, y: number, maxWidth: number): number {
  y = ensurePageSpace(doc, y, LINE_HEIGHT * 2);
  y = writeWrappedText(doc, text, x, y, maxWidth, HEADING_SIZE, "bold");
  return y + 2;
}

export function generateReportPdf({
  reportText,
  companyName,
  collectedData,
}: {
  reportText: string;
  companyName: string;
  collectedData: CollectedDataSection[];
}): void {
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const pageWidth = doc.internal.pageSize.getWidth();
  const maxWidth = pageWidth - MARGIN * 2;
  let y = MARGIN;

  const displayCompany = companyName && companyName !== "Your Company" ? companyName : "Your Company";

  y = writeWrappedText(doc, "Quantum Readiness Report", MARGIN, y, maxWidth, TITLE_SIZE, "bold");
  y += 2;
  y = writeWrappedText(doc, `Company: ${displayCompany}`, MARGIN, y, maxWidth, BODY_SIZE, "bold");
  y += 4;

  const reportBody = markdownToPlainText(reportText);
  y = writeWrappedText(doc, reportBody, MARGIN, y, maxWidth, BODY_SIZE);

  const appendixAlreadyInReport = reportIncludesCollectedData(reportText);
  if (!appendixAlreadyInReport && collectedData.length > 0) {
    y += 6;
    y = ensurePageSpace(doc, y, LINE_HEIGHT * 4);
    doc.setDrawColor(47, 65, 86);
    doc.line(MARGIN, y, pageWidth - MARGIN, y);
    y += 8;
    y = writeSectionHeading(doc, "Appendix: Collected Assessment Data", MARGIN, y, maxWidth);
    y = writeWrappedText(
      doc,
      "This section captures the information gathered during the readiness assessment. Use it as context when continuing with the Roadmap Chatbot.",
      MARGIN,
      y,
      maxWidth,
      SMALL_SIZE
    );
    y += 3;

    for (const section of collectedData) {
      y = writeSectionHeading(doc, section.title, MARGIN, y, maxWidth);
      y = writeWrappedText(doc, section.content, MARGIN, y, maxWidth, BODY_SIZE);
      y += 3;
    }
  }

  const filename = `${sanitizeFilename(displayCompany)}-quantum-readiness-report.pdf`;
  doc.save(filename);
}
