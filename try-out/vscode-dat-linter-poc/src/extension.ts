import * as vscode from "vscode";
import { execFile } from "child_process";
import * as path from "path";
import { parseDatLinterLines, toVscodeDiagnostics } from "./parser";

let diagnosticCollection: vscode.DiagnosticCollection;

export function activate(context: vscode.ExtensionContext): void {
  diagnosticCollection = vscode.languages.createDiagnosticCollection("dat-linter");
  context.subscriptions.push(diagnosticCollection);

  const maybeLint = (document: vscode.TextDocument) => {
    if (!isDatFile(document)) {
      return;
    }
    void lintDocument(document);
  };

  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument(maybeLint),
    vscode.workspace.onDidOpenTextDocument(maybeLint),
    vscode.workspace.onDidCloseTextDocument((doc) => {
      diagnosticCollection.delete(doc.uri);
    })
  );

  // Lint any .dat documents that were already open when the extension activated.
  vscode.workspace.textDocuments.forEach(maybeLint);
}

export function deactivate(): void {
  diagnosticCollection?.dispose();
}

function isDatFile(document: vscode.TextDocument): boolean {
  return (
    document.uri.scheme === "file" &&
    document.fileName.toLowerCase().endsWith(".dat")
  );
}

async function lintDocument(document: vscode.TextDocument): Promise<void> {
  const filePath = document.uri.fsPath;
  const cwd = path.dirname(filePath);
  const config = vscode.workspace.getConfiguration("datLinterPoc");
  const executablePath = config.get<string>("executablePath", "dat_linter");
  const configPath = config.get<string>("configPath", "");

  const args = ["lint", filePath];
  if (configPath) {
    args.push("--config", configPath);
  }

  try {
    const output = await runDatLinter(executablePath, args, cwd);
    // NOTE: dat_linter writes per-diagnostic lines to stderr and only the trailing
    // "N error(s) / M warning(s)" summary line to stdout (discovered by this PoC's
    // integration tests; see README.md). Both streams are parsed together so the
    // extension keeps working regardless of which stream a given line lands on.
    const parsed = parseDatLinterLines(`${output.stdout}\n${output.stderr}`);
    const diagnostics = toVscodeDiagnostics(parsed, document);
    diagnosticCollection.set(document.uri, diagnostics);
  } catch (err) {
    // dat_linter exits with a non-zero code whenever it reports at least one
    // error-level diagnostic (see runDatLinter, which still resolves in that case).
    // This catch only fires for genuine failures to run the tool at all (e.g.
    // executable not found), which we surface once via a notification rather than
    // silently dropping.
    const message = err instanceof Error ? err.message : String(err);
    void vscode.window.showErrorMessage(`dat_linter: failed to run (${message})`);
  }
}

interface DatLinterOutput {
  stdout: string;
  stderr: string;
}

/**
 * Runs dat_linter and resolves with both stdout and stderr. dat_linter's exit code
 * reflects whether error-level diagnostics were found (non-zero = at least one
 * error), NOT whether the process itself failed to run — so a non-zero exit with
 * usable output is treated as success here, and only a spawn failure (no output at
 * all) is treated as an error.
 */
function runDatLinter(executablePath: string, args: string[], cwd: string): Promise<DatLinterOutput> {
  return new Promise((resolve, reject) => {
    execFile(executablePath, args, { cwd }, (error, stdout, stderr) => {
      if (stdout !== undefined || stderr !== undefined) {
        resolve({ stdout: stdout ?? "", stderr: stderr ?? "" });
        return;
      }
      reject(error ?? new Error("dat_linter produced no output"));
    });
  });
}
