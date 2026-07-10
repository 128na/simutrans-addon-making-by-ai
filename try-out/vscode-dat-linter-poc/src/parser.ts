import * as vscode from "vscode";

/**
 * Parses the plain-text output of `dat_linter lint <path>` into VSCode diagnostics.
 *
 * dat_linter has no structured (JSON) output mode; it emits one diagnostic per line in
 * one of two shapes, plus a trailing summary line that must be ignored:
 *
 *   path: [severity] code (line N): message       (diagnostic tied to a specific line)
 *   path: [severity] code: message                 (file-wide diagnostic, no line number)
 *   path: N error(s) / M warning(s)                (summary line — not a diagnostic)
 *
 * severity is one of: error | warn | info | debug
 *
 * Diagnostics without a line number are reported on line 0 (VSCode line 0, i.e. the
 * document's first line) since dat_linter gives no better anchor.
 */

const DIAGNOSTIC_LINE_RE =
  /^.+?: \[(error|warn|info|debug)\] ([a-zA-Z0-9_-]+)(?: \(line (\d+)\))?: (.*)$/;

function mapSeverity(sev: string): vscode.DiagnosticSeverity {
  switch (sev) {
    case "error":
      return vscode.DiagnosticSeverity.Error;
    case "warn":
      return vscode.DiagnosticSeverity.Warning;
    case "info":
      return vscode.DiagnosticSeverity.Information;
    case "debug":
      return vscode.DiagnosticSeverity.Hint;
    default:
      return vscode.DiagnosticSeverity.Warning;
  }
}

export interface ParsedDiagnostic {
  /** 0-indexed line number (dat_linter reports 1-indexed lines; -1 means "no line given"). */
  line: number;
  severity: vscode.DiagnosticSeverity;
  code: string;
  message: string;
}

/**
 * Pure parsing step, independent of vscode.Diagnostic construction, to keep the
 * regex/mapping logic easy to unit-test in isolation from the extension host.
 */
export function parseDatLinterLines(stdout: string): ParsedDiagnostic[] {
  const results: ParsedDiagnostic[] = [];
  const lines = stdout.split(/\r?\n/);

  for (const rawLine of lines) {
    if (rawLine.trim().length === 0) {
      continue;
    }
    const match = DIAGNOSTIC_LINE_RE.exec(rawLine);
    if (!match) {
      // Not a diagnostic line (e.g. the "N error(s) / M warning(s)" summary line, or
      // stray stderr/tool noise that made it into stdout). Skip it.
      continue;
    }
    const [, severity, code, lineNoStr, message] = match;
    const oneIndexedLine = lineNoStr ? parseInt(lineNoStr, 10) : undefined;
    results.push({
      line: oneIndexedLine !== undefined ? oneIndexedLine - 1 : -1,
      severity: mapSeverity(severity),
      code,
      message,
    });
  }

  return results;
}

/**
 * Converts parsed diagnostics into vscode.Diagnostic objects anchored to a document.
 * Diagnostics with no line number (line === -1) fall back to the document's first line.
 */
export function toVscodeDiagnostics(
  parsed: ParsedDiagnostic[],
  document: vscode.TextDocument
): vscode.Diagnostic[] {
  return parsed.map((p) => {
    const lineNo = p.line >= 0 ? Math.min(p.line, document.lineCount - 1) : 0;
    const lineText = document.lineCount > 0 ? document.lineAt(lineNo).text : "";
    const range = new vscode.Range(
      lineNo,
      0,
      lineNo,
      Math.max(lineText.length, 1)
    );
    const diagnostic = new vscode.Diagnostic(range, p.message, p.severity);
    diagnostic.code = p.code;
    diagnostic.source = "dat_linter";
    return diagnostic;
  });
}
