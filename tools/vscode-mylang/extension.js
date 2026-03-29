const vscode = require('vscode');
const cp = require('child_process');
const path = require('path');

class JsonRpcConnection {
  constructor(command, args, cwd) {
    this.proc = cp.spawn(command, args, { cwd, stdio: ['pipe', 'pipe', 'inherit'] });
    this.nextId = 1;
    this.pending = new Map();
    this.buffer = Buffer.alloc(0);
    this.proc.stdout.on('data', (chunk) => this.onData(chunk));
    this.proc.on('exit', () => {
      for (const [, pending] of this.pending) {
        pending.reject(new Error('MyLang LSP exited'));
      }
      this.pending.clear();
    });
  }

  onData(chunk) {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    while (true) {
      const headerEnd = this.buffer.indexOf('\r\n\r\n');
      if (headerEnd < 0) return;
      const header = this.buffer.slice(0, headerEnd).toString('utf8');
      const match = header.match(/Content-Length:\s*(\d+)/i);
      if (!match) {
        this.buffer = this.buffer.slice(headerEnd + 4);
        continue;
      }
      const length = Number(match[1]);
      const total = headerEnd + 4 + length;
      if (this.buffer.length < total) return;
      const body = this.buffer.slice(headerEnd + 4, total).toString('utf8');
      this.buffer = this.buffer.slice(total);
      const msg = JSON.parse(body);
      if (Object.prototype.hasOwnProperty.call(msg, 'id') && this.pending.has(msg.id)) {
        const pending = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) pending.reject(new Error(msg.error.message || 'LSP error'));
        else pending.resolve(msg.result);
      }
    }
  }

  send(payload) {
    const text = JSON.stringify(payload);
    const bytes = Buffer.from(text, 'utf8');
    this.proc.stdin.write(`Content-Length: ${bytes.length}\r\n\r\n`);
    this.proc.stdin.write(bytes);
  }

  request(method, params) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.send({ jsonrpc: '2.0', id, method, params });
    });
  }

  notify(method, params) {
    this.send({ jsonrpc: '2.0', method, params });
  }

  dispose() {
    try {
      this.notify('exit', {});
    } catch (_) {}
    this.proc.kill();
  }
}

function documentSelector() {
  return [{ language: 'mylang', scheme: 'file' }];
}

function toTextDocumentItem(doc) {
  return {
    uri: doc.uri.toString(),
    languageId: doc.languageId,
    version: doc.version,
    text: doc.getText(),
  };
}

async function activate(context) {
  const config = vscode.workspace.getConfiguration('mylang');
  const pythonPath = config.get('lsp.pythonPath') || 'python3';
  const semanticTokensEnabled = config.get('lsp.semanticTokens') === true;
  const fs = require('fs');
  const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  const serverPath = workspaceRoot ? path.join(workspaceRoot, 'tools', 'MyLangServerProtocol', 'server.py') : null;
  if (!serverPath || !fs.existsSync(serverPath)) {
    vscode.window.showErrorMessage('MyLangServerProtocol submodule was not found. Run git submodule update --init --recursive.');
    return;
  }
  const cwd = path.dirname(serverPath);
  const rpc = new JsonRpcConnection(pythonPath, [serverPath], cwd);
  context.subscriptions.push({ dispose: () => rpc.dispose() });

  const initResult = await rpc.request('initialize', {
    processId: process.pid,
    clientInfo: { name: 'mylang-vscode', version: '0.1.0' },
    rootUri: vscode.workspace.workspaceFolders?.[0]?.uri.toString() || null,
    capabilities: {}
  });
  rpc.notify('initialized', {});

  for (const doc of vscode.workspace.textDocuments) {
    if (doc.languageId === 'mylang') {
      rpc.notify('textDocument/didOpen', { textDocument: toTextDocumentItem(doc) });
    }
  }

  context.subscriptions.push(vscode.workspace.onDidOpenTextDocument((doc) => {
    if (doc.languageId !== 'mylang') return;
    rpc.notify('textDocument/didOpen', { textDocument: toTextDocumentItem(doc) });
  }));

  context.subscriptions.push(vscode.workspace.onDidChangeTextDocument((event) => {
    if (event.document.languageId !== 'mylang') return;
    rpc.notify('textDocument/didChange', {
      textDocument: { uri: event.document.uri.toString(), version: event.document.version },
      contentChanges: [{ text: event.document.getText() }],
    });
  }));

  context.subscriptions.push(vscode.workspace.onDidCloseTextDocument((doc) => {
    if (doc.languageId !== 'mylang') return;
    rpc.notify('textDocument/didClose', { textDocument: { uri: doc.uri.toString() } });
  }));

  if (semanticTokensEnabled && initResult.capabilities.semanticTokensProvider) {
    const legend = new vscode.SemanticTokensLegend(
      initResult.capabilities.semanticTokensProvider.legend.tokenTypes,
      initResult.capabilities.semanticTokensProvider.legend.tokenModifiers,
    );

    context.subscriptions.push(vscode.languages.registerDocumentSemanticTokensProvider(documentSelector(), {
      provideDocumentSemanticTokens: async (doc) => {
        const result = await rpc.request('textDocument/semanticTokens/full', {
          textDocument: { uri: doc.uri.toString() }
        });
        return new vscode.SemanticTokens(new Uint32Array(result.data));
      }
    }, legend));
  }

  context.subscriptions.push(vscode.languages.registerDocumentSymbolProvider(documentSelector(), {
    provideDocumentSymbols: async (doc) => {
      const result = await rpc.request('textDocument/documentSymbol', {
        textDocument: { uri: doc.uri.toString() }
      });
      return result.map((sym) => {
        const range = new vscode.Range(sym.range.start.line, sym.range.start.character, sym.range.end.line, sym.range.end.character);
        const selectionRange = new vscode.Range(sym.selectionRange.start.line, sym.selectionRange.start.character, sym.selectionRange.end.line, sym.selectionRange.end.character);
        return new vscode.DocumentSymbol(sym.name, '', sym.kind, range, selectionRange);
      });
    }
  }));
}

function deactivate() {}

module.exports = { activate, deactivate };
