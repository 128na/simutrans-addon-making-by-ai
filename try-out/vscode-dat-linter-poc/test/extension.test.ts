import * as assert from "assert";
import * as path from "path";
import * as vscode from "vscode";

// package.json publisher "poc" + name "vscode-dat-linter-poc"
const EXTENSION_ID = "poc.vscode-dat-linter-poc";

// out/test -> out -> vscode-dat-linter-poc -> try-out -> simutrans_addon
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..", "..");
const TESTDATA_DIR = path.join(REPO_ROOT, "refs", "simutrans-dat-linter", "testdata");
// out/test -> out -> vscode-dat-linter-poc, then fixtures/test-lint-config.toml
const FIXTURE_CONFIG = path.resolve(__dirname, "..", "..", "fixtures", "test-lint-config.toml");

/**
 * Polls vscode.languages.getDiagnostics until predicate is satisfied, since
 * diagnosticCollection.set() happens asynchronously after dat_linter's child
 * process exits.
 */
async function waitForDiagnostics(
  uri: vscode.Uri,
  predicate: (diags: readonly vscode.Diagnostic[]) => boolean,
  timeoutMs = 15000
): Promise<readonly vscode.Diagnostic[]> {
  const start = Date.now();
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const diags = vscode.languages.getDiagnostics(uri);
    if (predicate(diags)) {
      return diags;
    }
    if (Date.now() - start > timeoutMs) {
      throw new Error(
        `Timed out waiting for diagnostics on ${uri.fsPath}. Last seen: ${JSON.stringify(
          diags.map((d) => ({ code: d.code, message: d.message }))
        )}`
      );
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
}

suite("dat_linter PoC integration", () => {
  suiteSetup(async function () {
    this.timeout(30000);
    const ext = vscode.extensions.getExtension(EXTENSION_ID);
    assert.ok(ext, `extension ${EXTENSION_ID} not found - is it registered under that id?`);
    await ext!.activate();

    // Point the extension at a throwaway config so dat_linter never falls back to
    // auto-generating dat_linter.toml next to the (read-only, ref-only) testdata files.
    const config = vscode.workspace.getConfiguration("datLinterPoc");
    await config.update(
      "configPath",
      FIXTURE_CONFIG,
      vscode.ConfigurationTarget.Global
    );
  });

  test("duplicate_key.dat produces a duplicate-key Warning on the correct 0-indexed line", async () => {
    const filePath = path.join(TESTDATA_DIR, "duplicate_key.dat");
    const uri = vscode.Uri.file(filePath);
    const document = await vscode.workspace.openTextDocument(uri);
    await vscode.window.showTextDocument(document);

    const diags = await waitForDiagnostics(uri, (d) => d.length > 0);

    const dup = diags.find((d) => d.code === "duplicate-key");
    assert.ok(
      dup,
      `expected a duplicate-key diagnostic, got: ${JSON.stringify(
        diags.map((d) => ({ code: d.code, severity: d.severity, message: d.message }))
      )}`
    );
    assert.strictEqual(dup!.severity, vscode.DiagnosticSeverity.Warning);
    // dat_linter's CLI output says "(line 3)" (1-indexed); VSCode ranges are
    // 0-indexed, so the diagnostic must land on line 2.
    assert.strictEqual(dup!.range.start.line, 2);
  });

  test("broken_missing_waytype.dat produces a missing-waytype Error falling back to line 0", async () => {
    const filePath = path.join(TESTDATA_DIR, "broken_missing_waytype.dat");
    const uri = vscode.Uri.file(filePath);
    const document = await vscode.workspace.openTextDocument(uri);
    await vscode.window.showTextDocument(document);

    const diags = await waitForDiagnostics(uri, (d) => d.length > 0);

    const missing = diags.find((d) => d.code === "missing-waytype");
    assert.ok(
      missing,
      `expected a missing-waytype diagnostic, got: ${JSON.stringify(
        diags.map((d) => ({ code: d.code, severity: d.severity, message: d.message }))
      )}`
    );
    assert.strictEqual(missing!.severity, vscode.DiagnosticSeverity.Error);
    // dat_linter gave no "(line N)" for this diagnostic (it's file-wide), so the
    // extension must fall back to line 0.
    assert.strictEqual(missing!.range.start.line, 0);
  });
});
