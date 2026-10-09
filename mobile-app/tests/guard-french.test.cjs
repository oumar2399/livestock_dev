/* global __dirname */
// Guard: no French in the app's UI text (Phase 4, finding A14).
//
// Checks the text a user can see: string literals, template text and JSX text in src/
// (parsed with the TypeScript compiler, so comments are never checked), and the strings of
// app.json (e.g. the iOS permission prompts). Not checked: import paths, property names,
// type literals. Allowed: the behaviour-correction values stored before Phase 4
// (feedbackLabels.ts LEGACY_CORRECTION_CODES), which are data. Backend messages are guarded
// by backend/tests/test_guard_french.py.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const ts = require('typescript');
const { loadTypeScript } = require('./helpers/load-typescript.cjs');

const SRC = path.join(__dirname, '../src');
const APP_JSON = path.join(__dirname, '../app.json');

const ACCENTED = /[àâäçéèêëîïôöùûüÿœæÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸŒÆ]/;
// Whole words only, never next to a hyphen ("non-null", "sans-serif" stay English).
const FRENCH_WORDS = new RegExp('(?<![\\p{L}\\d_-])(le|la|les|des|du|une|avec|dans|sur|vos|votre|nous|vous|est'
  + '|sont|pas|aucun|aucune|il y a|erreur|chargement|annuler|enregistrer|supprimer|fermer|valider|modifier'
  + '|ajouter|connexion|paramètres|ferme|animaux|collier|colliers|troupeau|appareil|oui|non)(?![\\p{L}\\d_-])', 'iu');

const looksFrench = (text) => ACCENTED.test(text) || FRENCH_WORDS.test(text);

/** UI text of one TS/TSX source: [line, text] pairs. */
function uiStrings(fileName, source) {
  const file = ts.createSourceFile(fileName, source, ts.ScriptTarget.Latest, true,
    fileName.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const found = [];
  const add = (node, text) => {
    if (text.trim()) found.push([file.getLineAndCharacterOfPosition(node.getStart(file)).line + 1, text]);
  };
  const visit = (node) => {
    const parent = node.parent;
    const isName = parent && (ts.isPropertyAssignment(parent) || ts.isPropertySignature(parent)) && parent.name === node;
    const isModulePath = parent && (ts.isImportDeclaration(parent) || ts.isExportDeclaration(parent)
      || ts.isExternalModuleReference(parent)
      || (ts.isCallExpression(parent) && parent.expression.getText(file) === 'require'));
    const isType = parent && ts.isLiteralTypeNode(parent);
    if ((ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) && !isName && !isModulePath && !isType) {
      add(node, node.text);
    } else if (ts.isTemplateHead(node) || ts.isTemplateMiddle(node) || ts.isTemplateTail(node)) {
      add(node, node.text);
    } else if (ts.isJsxText(node)) {
      add(node, node.text);
    }
    ts.forEachChild(node, visit);
  };
  visit(file);
  return found;
}

function sourceFiles(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(full);
    return /\.(ts|tsx)$/.test(entry.name) ? [full] : [];
  });
}

function jsonStrings(value) {
  if (typeof value === 'string') return [value];
  if (Array.isArray(value)) return value.flatMap(jsonStrings);
  if (value && typeof value === 'object') return Object.values(value).flatMap(jsonStrings);
  return [];
}

test('the detector reads UI text only and flags French in it', () => {
  const source = `
    // Commentaire en français : ignoré.
    import x from './données';
    const label = 'Annuler';
    const ok = 'Value must be non-null';
    export const view = <Text>Dernière synchronisation</Text>;
  `;
  const flagged = uiStrings('sample.tsx', source).filter(([, text]) => looksFrench(text)).map(([, text]) => text.trim());
  assert.deepEqual(flagged, ['Annuler', 'Dernière synchronisation']);
  assert.equal(looksFrench('font: sans-serif; non-null; Close; Save'), false);
});

test('no French in the app UI text (src/) and app.json', () => {
  const legacy = new Set(Object.keys(loadTypeScript(path.join(SRC, 'utils/feedbackLabels.ts')).LEGACY_CORRECTION_CODES));
  const problems = [];
  for (const file of sourceFiles(SRC)) {
    for (const [line, text] of uiStrings(file, fs.readFileSync(file, 'utf8'))) {
      const allowed = file.endsWith(path.join('utils', 'feedbackLabels.ts')) && legacy.has(text);
      if (!allowed && looksFrench(text)) problems.push(`${path.relative(SRC, file)}:${line}: ${text.trim().slice(0, 80)}`);
    }
  }
  for (const text of jsonStrings(JSON.parse(fs.readFileSync(APP_JSON, 'utf8')))) {
    if (looksFrench(text)) problems.push(`app.json: ${text.slice(0, 80)}`);
  }
  assert.deepEqual(problems, [], 'French UI text:\n' + problems.join('\n'));
});
