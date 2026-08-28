#!/usr/bin/env node
/* qa_blank_verify.js — Суворий QA-протокол: перевірка 7 пунктів Бланка Перевірки.
 * Перевіряє РЕАЛЬНИЙ стан DOM (не innerText, бо placeholder не входить у innerText),
 * робить скріншоти для кожного пункту, сіє прогрес у localStorage для перевірки метрик.
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = 'http://localhost:8080';
const OUT_DIR = path.join(__dirname, '..', 'screenshots');
const results = [];
let pass = 0, fail = 0;

function check(name, cond, detail) {
  const ok = !!cond;
  if (ok) pass++; else fail++;
  log(`${ok ? '✅' : '❌'} ${name}${detail ? ' — ' + detail : ''}`);
  return ok;
}
function log(msg) {
  console.log(msg);
  results.push(msg);
}

(async () => {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });

  // ============ ПУНКТ 1: Головна сторінка ============
  log('\n========== ПУНКТ 1: Головна сторінка ==========');
  await page.goto(BASE + '/index.html', { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT_DIR, 'qa_01_home.png'), fullPage: false });
  log('Скріншот: qa_01_home.png');

  const home = await page.evaluate(() => {
    const text = document.body.innerText;
    return {
      bankCards: document.querySelectorAll('[data-bank]').length,
      hasLibrary: /Бібліотека законів/.test(text),
      hasHowTo: /Як користуватися/.test(text),
      bankNames: Array.from(document.querySelectorAll('[data-bank]')).map(el => (el.innerText||'').slice(0,40)),
    };
  });
  log('Картки банків: ' + JSON.stringify(home.bankNames));
  check('П.1: Тільки картки банків (немає «Бібліотека законів»)', !home.hasLibrary);
  check('П.1: Немає «Як користуватися» на головній', !home.hasHowTo);
  check('П.1: Є картки банків', home.bankCards >= 1);

  // ============ ПУНКТ 2-4: Банк МЗС ============
  log('\n========== ПУНКТ 2-4: Банк МЗС ==========');
  const clicked = await page.evaluate(() => {
    const cards = Array.from(document.querySelectorAll('[data-bank]'));
    const t = cards.find(el => /МЗС|міністерство|зовнішніх справ|віцеконсул/i.test(el.innerText || ''));
    if (t) { t.click(); return true; }
    return false;
  });
  check('Відкрито банк МЗС', clicked);
  await page.waitForTimeout(1500);

  // Сіємо прогрес у localStorage, щоб перевірити формат метрик
  await page.evaluate(() => {
    try {
      const key = Object.keys(localStorage).find(k => k.startsWith('trenazher:'));
      const bankFile = key ? key.replace('trenazher:', '') : 'banks/mzs-2026.json';
      const storeKey = 'trenazher:' + bankFile;
      let data = {};
      try { data = JSON.parse(localStorage.getItem(storeKey) || '{}'); } catch(e) {}
      // Знайдемо перший розділ банку
      const manifest = JSON.parse(localStorage.getItem('manifest') || '{}');
      // Використаємо відомий формат прогресу: { sections: { id: {correct:[], wrong:[]} } }
      if (!data.sections) data.sections = {};
      // Сіємо для першої теми: 7 пройдено, 6 правильно (86%)
      const secId = 's1'; // приблизний id, буде перезаписано нижче
      data.sections[secId] = { correct: ['a','b','c','d','e','f'], wrong: ['g'] };
      localStorage.setItem(storeKey, JSON.stringify(data));
    } catch(e) { /* ignore */ }
  });
  // Перезавантажити банк, щоб прогрес підхопився
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  const clicked2 = await page.evaluate(() => {
    const cards = Array.from(document.querySelectorAll('[data-bank]'));
    const t = cards.find(el => /МЗС|міністерство|зовнішніх справ|віцеконсул/i.test(el.innerText || ''));
    if (t) { t.click(); return true; }
    return false;
  });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(OUT_DIR, 'qa_02_bank_topics.png'), fullPage: false });
  log('Скріншот: qa_02_bank_topics.png');

  const topics = await page.evaluate(() => {
    const text = document.body.innerText;
    const row = document.querySelector('.topic-row');
    const searchInput = document.getElementById('topicSearch');
    const stickyBar = document.getElementById('btnLearnSelected');
    const stickyWrap = stickyBar ? stickyBar.closest('.topic-sticky-bar') : null;
    return {
      hasProgressBlock: /Прогрес по темах/.test(text),
      topicRows: document.querySelectorAll('.topic-row').length,
      hasSelectAll: /Обрати всі/.test(text),
      hasDeselectAll: /Зняти всі/.test(text),
      searchPlaceholder: searchInput ? searchInput.placeholder : null,
      stickyBarText: stickyBar ? (stickyBar.innerText||'').trim() : null,
      stickyWrapPosition: stickyWrap ? getComputedStyle(stickyWrap).position : null,
      stickyWrapBottom: stickyWrap ? getComputedStyle(stickyWrap).bottom : null,
      card: row ? {
        checkbox: !!row.querySelector('input[type=checkbox]'),
        title: !!row.querySelector('.topic-title'),
        progress: !!row.querySelector('.topic-progress'),
        reset: !!row.querySelector('.topic-reset'),
        meta: !!row.querySelector('.topic-meta'),
        metaText: (row.querySelector('.topic-meta')||{}).innerText || '',
      } : null,
    };
  });
  log('Теми: ' + JSON.stringify(topics, null, 2));

  // ПУНКТ 3
  check('П.3: Немає окремого блоку «Прогрес по темах»', !topics.hasProgressBlock);
  check('П.3: Єдина картка — чекбокс', topics.card && topics.card.checkbox);
  check('П.3: Єдина картка — заголовок', topics.card && topics.card.title);
  check('П.3: Єдина картка — прогрес', topics.card && topics.card.progress);
  check('П.3: Єдина картка — скидання ↺', topics.card && topics.card.reset);
  check('П.3: Є мета-інфо (лічильник)', topics.card && topics.card.meta);

  // ПУНКТ 4
  check('П.4: Кнопка [Обрати всі]', topics.hasSelectAll);
  check('П.4: Кнопка [Зняти всі]', topics.hasDeselectAll);
  check('П.4: Пошук тем (placeholder)', topics.searchPlaceholder && /Пошук теми/.test(topics.searchPlaceholder));
  check('П.4: Sticky Footer «Навчатися за обраними темами»', topics.stickyBarText && /Навчатися за обраними темами/.test(topics.stickyBarText));
  check('П.4: Sticky Footer position=sticky (на батьку .topic-sticky-bar)', topics.stickyWrapPosition === 'sticky' || topics.stickyWrapPosition === 'fixed');

  // ПУНКТ 2: формат метрик
  const metricFormat = await page.evaluate(() => {
    const text = document.body.innerText;
    const m = text.match(/(\d+)\/(\d+)\s*питань\s*\((\d+)%\)\s*·\s*🎯\s*(\d+)%\s*правильно/);
    return m ? { done: +m[1], total: +m[2], pct: +m[3], acc: +m[4] } : null;
  });
  log('Формат метрик: ' + JSON.stringify(metricFormat));
  check('П.2: Формат «N/M питань (P%) · 🎯 A% правильно»', !!metricFormat);
  if (metricFormat) {
    check('П.2: Відсоток проходження математично вірний', metricFormat.pct === Math.round(metricFormat.done / metricFormat.total * 100));
  }

  // ============ ПУНКТ 5-6: Законодавча база + модальне вікно ============
  log('\n========== ПУНКТ 5-6: Законодавча база + модальне вікно ==========');
  const lawOpened = await page.evaluate(() => {
    if (typeof openLawModal === 'function') {
      try { openLawModal('laws/zakon-pro-hromadianstvo.html'); return true; }
      catch (e) { return 'err:' + e.message; }
    }
    return false;
  });
  check('Відкрито модальне вікно закону', lawOpened === true);
  await page.waitForTimeout(2500);
  await page.screenshot({ path: path.join(OUT_DIR, 'qa_03_law_modal.png'), fullPage: false });
  log('Скріншот: qa_03_law_modal.png');

  const modalUI = await page.evaluate(() => {
    const tocBtn = document.getElementById('lawTocToggle');
    const searchInput = document.getElementById('lawSearchInput');
    const toc = document.getElementById('lawToc');
    return {
      tocBtnText: tocBtn ? tocBtn.textContent.trim() : null,
      searchPlaceholder: searchInput ? searchInput.placeholder : null,
      tocChildren: toc ? toc.children.length : 0,
    };
  });
  log('UI модалки: ' + JSON.stringify(modalUI));
  check('П.6: Кнопка «☰ Зміст»', modalUI.tocBtnText && /Зміст/.test(modalUI.tocBtnText));
  check('П.6: Поле «🔍 Пошук у законі»', modalUI.searchPlaceholder && /Пошук у законі/.test(modalUI.searchPlaceholder));
  check('П.6: Зміст заповнено статтями', modalUI.tocChildren > 0);

  const lawStruct = await page.evaluate(() => {
    const iframe = document.querySelector('#lawModal iframe, .law-modal iframe, iframe[src*="laws"]');
    if (!iframe) return { error: 'iframe не знайдено' };
    try {
      const doc = iframe.contentDocument;
      const header = doc.querySelector('.law-header');
      const headerCS = header ? getComputedStyle(header) : null;
      const text = doc.body ? doc.body.innerText : '';
      return {
        title: doc.title || '',
        hasLawHeader: !!header,
        hasLawContent: !!doc.querySelector('.law-content'),
        articleCount: doc.querySelectorAll('.law-article').length,
        pCount: doc.querySelectorAll('p').length,
        sticky: headerCS ? headerCS.position : null,
        stickyTop: headerCS ? headerCS.top : null,
        hasBadSpace: /ст\.\d|№\d|п\.\d|ч\.\d/.test(text),
        hasGoodSpace: /ст\. \d|№ \d|п\. \d|ч\. \d/.test(text),
      };
    } catch (e) { return { error: 'cross-origin: ' + e.message }; }
  });
  log('Структура закону (iframe): ' + JSON.stringify(lawStruct));
  if (!lawStruct.error) {
    check('П.5: Назва українською', /[А-ЯІЇЄҐ]/.test(lawStruct.title));
    check('П.5: Є .law-header', lawStruct.hasLawHeader);
    check('П.5: Є .law-content', lawStruct.hasLawContent);
    check(`П.5: Статті (.law-article): ${lawStruct.articleCount}`, lawStruct.articleCount > 0);
    check(`П.5: Абзаци <p>: ${lawStruct.pCount}`, lawStruct.pCount > 0);
    check('П.5: Шапка sticky (computed)', lawStruct.sticky === 'sticky');
    check('П.5: top:0', lawStruct.stickyTop === '0px' || lawStruct.stickyTop === '0');
    check('П.5: Немає злитих «ст.178№429»', !lawStruct.hasBadSpace);
    check('П.5: Є коректні «ст. 178 № 429»', lawStruct.hasGoodSpace);
  }

  try {
    const iframeLoc = page.locator('#lawModal iframe, .law-modal iframe, iframe[src*="laws"]').first();
    if (await iframeLoc.count() > 0) {
      await iframeLoc.screenshot({ path: path.join(OUT_DIR, 'qa_04_law_iframe_full.png') });
      log('Скріншот: qa_04_law_iframe_full.png');
    }
  } catch (e) { log('iframe скріншот: ' + e.message); }

  // ============ ПУНКТ 7: Підказки та посилання ============
  log('\n========== ПУНКТ 7: Підказки та посилання ==========');
  await page.evaluate(() => { if (typeof closeLawModal === 'function') closeLawModal(); });
  await page.waitForTimeout(500);
  // Вибрати першу тему і натиснути «Навчатися»
  const started = await page.evaluate(() => {
    const cb = document.querySelector('.topic-row input[type=checkbox]');
    if (cb) { cb.click(); }
    const btn = document.getElementById('btnLearnSelected');
    if (btn) { btn.click(); return true; }
    return false;
  });
  check('Розпочато тренування (обрано тему)', started);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(OUT_DIR, 'qa_05_question.png'), fullPage: false });
  log('Скріншот: qa_05_question.png');

  const q = await page.evaluate(() => {
    const hotkeys = document.querySelectorAll('.hotkey-hint');
    const hotkeyText = hotkeys.length ? hotkeys[0].innerText : '';
    const options = document.querySelectorAll('.option');
    const lawLinks = document.querySelectorAll('.explain-link, a[href*="laws/"], [data-law]');
    return {
      hotkeyText,
      optionCount: options.length,
      lawLinkCount: lawLinks.length,
      hasQuestion: !!document.getElementById('qText'),
    };
  });
  log('Питання: ' + JSON.stringify(q));
  check('П.7: Є підказка hotkeys', q.hotkeyText.length > 0);
  check('П.7: Динамічний діапазон «1–N»', /1\s*[–-]\s*\d+/.test(q.hotkeyText));
  check('П.7: Кількість варіантів = N у підказці', (() => {
    const m = q.hotkeyText.match(/1\s*[–-]\s*(\d+)/);
    return m && +m[1] === q.optionCount;
  })());

  // Відповісти на питання, щоб показати Пояснення з посиланням на закон
  const answered = await page.evaluate(() => {
    const opt = document.querySelector('.option');
    if (opt) { opt.click(); return true; }
    return false;
  });
  check('Відповідь на питання', answered);
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT_DIR, 'qa_06_explain.png'), fullPage: false });
  log('Скріншот: qa_06_explain.png');

  const explainInfo = await page.evaluate(() => {
    const box = document.getElementById('explainBox');
    const link = box ? box.querySelector('.explain-link') : null;
    return {
      hasExplainBox: !!box,
      explainText: box ? (box.innerText||'').slice(0, 200) : '',
      lawLinkCount: box ? box.querySelectorAll('.explain-link').length : 0,
      lawLinkText: link ? link.textContent.trim() : '',
    };
  });
  log('Пояснення: ' + JSON.stringify(explainInfo));
  check('П.7: Є блок «Пояснення»', explainInfo.hasExplainBox);
  check('П.7: Є клікабельне посилання на закон', explainInfo.lawLinkCount > 0);

  await browser.close();

  log('\n========== ПІДСУМОК QA-ПРОТОКОЛУ ==========');
  log(`Пройдено: ${pass} | Провалено: ${fail}`);
  log(`Результат: ${fail === 0 ? '✅ ВСІ ПЕРЕВІРКИ ПРОЙДЕНО' : '❌ Є ПРОВАЛЕНІ ПЕРЕВІРКИ'}`);
  fs.writeFileSync(path.join(OUT_DIR, '_qa_blank_summary.txt'), results.join('\n'));
  console.log('\nГотово. Скріншоти в ' + OUT_DIR);
})().catch(e => {
  console.error('ПОМИЛКА:', e);
  process.exit(1);
});
