import ExcelJS from "exceljs";
import type { MatchResultDTO, ResultFilter } from "../types";
import { formatAlternativeLabel } from "../utils/alternatives";
import { formatGestionaleMatchLine } from "../utils/gestionaleMatch";

const FILTER_SUFFIX: Record<ResultFilter, string> = {
  all: "tutti",
  matched: "match",
  ambiguous: "ambigui",
};

const COLORS = {
  headerBg: "FF2A3344",
  headerText: "FFE8ECF4",
  border: "FFE2E8F0",
  text: "FF1C2230",
  matched: "FFE8F8F0",
  ambiguous: "FFFFF8E6",
  unmatched: "FFF8F9FB",
} as const;

const WRAP_COLUMNS = new Set([3, 7, 8]);

function outcomeLabel(row: MatchResultDTO): string {
  if (row.matched) return "Match";
  if (row.ambiguous) return "Ambiguo";
  return "Nessun match";
}

function rowFill(row: MatchResultDTO): string {
  if (row.matched) return COLORS.matched;
  if (row.ambiguous) return COLORS.ambiguous;
  return COLORS.unmatched;
}

function formatGestionaleCell(row: MatchResultDTO): string {
  if (row.gestionale.length > 0) {
    return row.gestionale
      .map((item) => formatGestionaleMatchLine(item.identificativo, item.description, item.amount))
      .join("\n");
  }
  if (row.alternatives.length > 0) {
    return row.alternatives
      .map((alt) => `Alt: ${formatAlternativeLabel(alt)} (${alt.confidence})`)
      .join("\n");
  }
  return "";
}

function parseAmount(value: string): number | null {
  const parsed = Number.parseFloat(value.replace(",", "."));
  return Number.isFinite(parsed) ? parsed : null;
}

function buildFilename(filter: ResultFilter): string {
  const date = new Date().toISOString().slice(0, 10);
  return `report-${FILTER_SUFFIX[filter]}-${date}.xlsx`;
}

function downloadBuffer(buffer: ArrayBuffer, filename: string): void {
  const blob = new Blob([buffer], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export async function exportReportXlsx(
  rows: MatchResultDTO[],
  filter: ResultFilter,
): Promise<void> {
  if (rows.length === 0) return;

  const workbook = new ExcelJS.Workbook();
  workbook.creator = "Trans Matching";
  workbook.created = new Date();

  const sheet = workbook.addWorksheet("Report", {
    views: [{ state: "frozen", ySplit: 1 }],
  });

  sheet.columns = [
    { header: "Riga", key: "row", width: 7 },
    { header: "Data", key: "date", width: 12 },
    { header: "Descrizione carta", key: "description", width: 34 },
    { header: "Importo", key: "amount", width: 14 },
    { header: "Esito", key: "outcome", width: 14 },
    { header: "Confidenza", key: "confidence", width: 12 },
    { header: "Gestionale", key: "gestionale", width: 40 },
    { header: "Motivazione", key: "reason", width: 46 },
    { header: "Strategia", key: "strategy", width: 12 },
    { header: "Trace ID", key: "traceId", width: 22 },
  ];

  for (const row of rows) {
    sheet.addRow({
      row: row.row_number,
      date: row.card.date,
      description: row.card.description,
      amount: parseAmount(row.card.amount),
      outcome: outcomeLabel(row),
      confidence: row.confidence,
      gestionale: formatGestionaleCell(row),
      reason: row.reason,
      strategy: row.strategy,
      traceId: row.trace_id,
    });
  }

  const header = sheet.getRow(1);
  header.height = 24;
  header.eachCell((cell) => {
    cell.font = {
      bold: true,
      color: { argb: COLORS.headerText },
      size: 11,
      name: "Calibri",
    };
    cell.fill = {
      type: "pattern",
      pattern: "solid",
      fgColor: { argb: COLORS.headerBg },
    };
    cell.alignment = { vertical: "middle", horizontal: "left" };
    cell.border = {
      bottom: { style: "thin", color: { argb: COLORS.headerBg } },
    };
  });

  sheet.eachRow((excelRow, rowNumber) => {
    if (rowNumber === 1) return;

    const source = rows[rowNumber - 2];
    const fill = rowFill(source);
    const gestionaleLines = formatGestionaleCell(source).split("\n").length;
    const reasonLines = (source.reason || "").split("\n").length;
    const lineCount = Math.max(gestionaleLines, reasonLines, 1);
    excelRow.height = Math.min(120, 18 + lineCount * 14);

    excelRow.eachCell({ includeEmpty: true }, (cell, colNumber) => {
      cell.fill = {
        type: "pattern",
        pattern: "solid",
        fgColor: { argb: fill },
      };
      cell.font = {
        size: 10,
        name: "Calibri",
        color: { argb: COLORS.text },
      };
      cell.alignment = {
        vertical: "top",
        horizontal: colNumber === 4 ? "right" : "left",
        wrapText: WRAP_COLUMNS.has(colNumber),
      };
      cell.border = {
        bottom: { style: "thin", color: { argb: COLORS.border } },
      };
    });

    const amountCell = excelRow.getCell(4);
    if (typeof amountCell.value === "number") {
      amountCell.numFmt = '#,##0.00 "€"';
    }
  });

  sheet.autoFilter = {
    from: { row: 1, column: 1 },
    to: { row: 1, column: sheet.columnCount },
  };

  const buffer = await workbook.xlsx.writeBuffer();
  downloadBuffer(buffer, buildFilename(filter));
}
