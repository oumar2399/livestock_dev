const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const ts = require('typescript');

// Exercise the actual TS/TSX source with native services substituted by the caller.
function loadTypeScript(filename, overrides = {}, cache = new Map()) {
  if (cache.has(filename)) return cache.get(filename).exports;
  const module = { exports: {} };
  cache.set(filename, module);
  const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.React, esModuleInterop: true },
    fileName: filename,
  }).outputText;
  const localRequire = createRequire(filename);
  const resolve = (name) => {
    if (Object.hasOwn(overrides, name)) return overrides[name];
    if (name.startsWith('.')) {
      const base = path.resolve(path.dirname(filename), name);
      const source = [base + '.ts', base + '.tsx'].find((file) => fs.existsSync(file));
      if (source) return loadTypeScript(source, overrides, cache);
    }
    return localRequire(name);
  };
  new Function('require', 'module', 'exports', compiled)(resolve, module, module.exports);
  return module.exports;
}

module.exports = { loadTypeScript };
