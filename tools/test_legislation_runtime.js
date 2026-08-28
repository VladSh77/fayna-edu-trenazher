#!/usr/bin/env node
// Функціональний тест runtime-логіки legislationLink проти реального банку.
// Імітує поведінку браузера: LEGISLATION масив + legislationLink(ref).
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf-8');

// Витягти LEGISLATION масив
const m = html.match(/const LEGISLATION = \[(.*?)\];/s);
if (!m) { console.error('LEGISLATION not found'); process.exit(1); }

// Оцінити масив через eval (безпечно — це локальний статичний файл)
const LEGISLATION = eval('[' + m[1] + ']');
console.log('LEGISLATION entries:', LEGISLATION.length);

// Відтворити legislationLink з index.html
function legislationLink(ref) {
  if (!ref) return null;
  const r = ref.toLowerCase();
  for (const [keys, file] of LEGISLATION) {
    for (const k of keys) {
      if (r.includes(k.toLowerCase())) return file;
    }
  }
  return null;
}

// Завантажити банк
const bank = JSON.parse(fs.readFileSync(path.join(ROOT, 'banks', 'mzs-2026.json'), 'utf-8'));

const KRAJ = [
  'конспект країнознавства','конституція республіки польща','карта поляка','карту поляка',
  'діловодство в польщі','історія польщі','гадяцький договір','загальні знання про єс',
  'загальні знання про консульську діяльність','законодавство польщі','історія україни',
  'закон про громадянство польщі','договір про добросусідство','люблінського трикутника',
  'статут організації об','зовнішню трудову міграцію','про інформацію','стратегія інформаційної безпеки',
  'закон про адвокатуру','закон про діловодство в польщі','закон про вибори до органів місцевого',
  'національні символи','державні свята','воєнний стан','національні меншини','адміністративний поділ',
  'валюту','міжнародну допомогу','про консульську службу'
];

let mapped = 0, kraj = 0, unmapped = [], missingFiles = [];
for (const s of bank.sections) {
  for (const q of s.questions || []) {
    const ref = (q.explain && q.explain.ref) || '';
    if (!ref) continue;
    const r = ref.toLowerCase();
    if (KRAJ.some(k => r.includes(k))) { kraj++; continue; }
    const file = legislationLink(ref);
    if (file) {
      mapped++;
      if (!fs.existsSync(path.join(ROOT, file))) missingFiles.push(file);
    } else {
      unmapped.push(q.id + ': ' + ref);
    }
  }
}

console.log('KRAJ refs:', kraj);
console.log('Mapped refs:', mapped);
console.log('Unmapped non-KRAJ:', unmapped.length);
unmapped.slice(0, 30).forEach(u => console.log('  ' + u));
console.log('Missing law files:', missingFiles.length ? missingFiles : 'NONE');

// Перевірка, що кожен файл у мапі існує
const mapMissing = LEGISLATION.filter(([, f]) => !fs.existsSync(path.join(ROOT, f))).map(([, f]) => f);
console.log('Map entries with missing file:', mapMissing.length ? mapMissing : 'NONE');

if (unmapped.length === 0 && missingFiles.length === 0 && mapMissing.length === 0) {
  console.log('\nRESULT: PASS — всі ref мапляться, всі файли існують');
} else {
  console.log('\nRESULT: FAIL');
  process.exit(1);
}
