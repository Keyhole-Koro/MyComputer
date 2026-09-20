const vscode = require('vscode');
const path = require('path');
const fs = require('fs');
const { LanguageClient } = require('vscode-languageclient/node');

let client;

function documentSelector() {
  return [{ language: 'mylang', scheme: 'file' }];
}

function findServerPath() {
  for (const folder of vscode.workspace.workspaceFolders || []) {
    const candidate = path.join(folder.uri.fsPath, 'tools', 'MyLangServerProtocol', 'server.py');
    if (fs.existsSync(candidate)) return candidate;
  }
  return null;
}

async function activate(context) {
  const serverPath = findServerPath();
  if (!serverPath) {
    vscode.window.showErrorMessage(
      'MyLangServerProtocol was not found in the workspace. Run git submodule update --init --recursive.',
    );
    return;
  }

  const config = vscode.workspace.getConfiguration('mylang');
  const pythonPath = config.get('lsp.pythonPath') || 'python3';
  const serverOptions = {
    command: pythonPath,
    args: [serverPath],
    options: { cwd: path.dirname(serverPath) },
  };
  const clientOptions = {
    documentSelector: documentSelector(),
    initializationOptions: {
      semanticTokens: config.get('lsp.semanticTokens') === true,
    },
    synchronize: {
      configurationSection: 'mylang',
      fileEvents: vscode.workspace.createFileSystemWatcher('**/*.{mln,mlx}'),
    },
    outputChannelName: 'MyLang Language Server',
  };

  client = new LanguageClient(
    'mylang',
    'MyLang Language Server',
    serverOptions,
    clientOptions,
  );
  context.subscriptions.push(client);
  await client.start();

  context.subscriptions.push(client.onNotification('mylang/hoverReady', async (params) => {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.uri.toString() !== params.uri) return;
    if (editor.document.version !== params.version) return;

    // VS Code has no standard LSP hover-refresh notification. If the request
    // came from the cursor position, close the loading hover and ask providers
    // again now that the server-side documentation cache is ready.
    const cursor = editor.selection.active;
    if (cursor.line !== params.position.line || cursor.character !== params.position.character) return;
    await vscode.commands.executeCommand('editor.action.hideHover');
    await vscode.commands.executeCommand('editor.action.showHover', { focus: 'noAutoFocus' });
  }));
}

async function deactivate() {
  if (client) {
    await client.stop();
    client = undefined;
  }
}

module.exports = { activate, deactivate };
