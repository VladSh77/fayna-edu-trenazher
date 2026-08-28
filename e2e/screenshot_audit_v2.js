#!/usr/bin/env node
/* screenshot_audit_v2.js
 * Візуальний аудит НОВОГО еталонного формату законів + оновлених сторінок.
 * Перевіряє РЕАЛЬНУ структуру (sticky-шапка, law-article блоки, укр. назва,
 * типографіка «ст. 178 № 429», Зміст, пошук) та робить скріншоти.
 * Використовує Playwright + локальний HTTP-сервер на :8080.
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = 'http://localhost:8080';
const OUT_DIR = path.join(__dirname, '..', 'screenshots');
const results = [];
let pass = 0, fail = 0;

function check(name, cond) {
  const ok = !!cond;
  if (ok) pass++; else fail++;
  log(`${ok ? '✅' : '❌'} ${name}`);
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

  // ---------- 1. Головна сторінка ----------
  log('\n=== 1. Головна сторінка ===');
  await page.goto(BASE + '/index.html', { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT_DIR, 'v2_01_home.png'), fullPage: false });
  log('Скріншот: v2_01_home.png');

  const homeText = await page.evaluate(() => document.body.innerText);
  check('Головна НЕ містить «Бібліотека законів»', !/Бібліотека законів/.test(homeText));
  check('Головна НЕ містить «Як користуватися»', !/Як користуватися/.test(homeText));
  const bankCards = await page.evaluate(() => document.querySelectorAll('[data-bank]').length);
  check(`Карток банків на головній: ${bankCards}`, bankCards >= 1);

  // ---------- 2. Банк МЗС — список тем ----------
  log('\n=== 2. Банк МЗС — список тем ===');
  const clicked = await page.evaluate(() => {
    const cards = Array.from(document.querySelectorAll('[data-bank]'));
    const target = cards.find(el => /МЗС|міністерство|зовнішніх справ|віцеконсул/i.test(el.innerText || ''));
    if (target) { target.click(); return true; }
    return false;
  });
  check('Клік по банку МЗС', clicked);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(OUT_DIR, 'v2_02_bank_topics.png'), fullPage: false });
  log('Скріншот: v2_02_bank_topics.png');

  const topicsInfo = await page.evaluate(() => {
    const text = document.body.innerText;
    return {
      hasProgressBlock: /Прогрес по темах/.test(text),
      hasQuickActions: /Обрати всі|Зняти всі|Тільки з помилками/.test(text),
      hasStickyBar: /Навчатися за обраними темами/.test(text),
      hasSearch: /Пошук теми|Фільтр тем/.test(text),
      topicRows: document.querySelectorAll('.topic-row').length,
      hasLawLib: /Бібліотека законів/.test(text),
    };
  });
  check('Окремий блок «Прогрес по темах» ВИДАЛЕНО', !topicsInfo.hasProgressBlock);
  check('Quick Actions Toolbar (Обрати всі/Зняти всі)', topicsInfo.hasQuickActions);
  check('Sticky Action Bar «Навчатися за обраними темами»', topicsInfo.hasStickyBar);
  check('Пошук тем', topicsInfo.hasSearch);
  check(`Рядків тем (.topic-row): ${topicsInfo.topicRows}`, topicsInfo.topicRows > 0);
  check('«Бібліотека законів» всередині банку МЗС', topicsInfo.hasLawLib);

  // Структура єдиної картки теми
  const cardStructure = await page.evaluate(() => {
    const row = document.querySelector('.topic-row');
    if (!row) return { error: 'немає .topic-row' };
    return {
      hasCheckbox: !!row.querySelector('input[type=checkbox]'),
      hasTitle: !!row.querySelector('.topic-title'),
      hasProgress: !!row.querySelector('.topic-progress'),
      hasReset: !!row.querySelector('.topic-reset'),
      hasMeta: !!row.querySelector('.topic-meta'),
    };
  });
  log('Структура картки теми: ' + JSON.stringify(cardStructure));
  check('Картка: чекбокс', cardStructure.hasCheckbox);
  check('Картка: заголовок', cardStructure.hasTitle);
  check('Картка: прогрес', cardStructure.hasProgress);
  check('Картка: скидання ↺', cardStructure.hasReset);

  // ---------- 3. Модальне вікно закону (новий еталонний формат) ----------
  log('\n=== 3. Модальне вікно закону (еталонний формат) ===');
  const lawOpened = await page.evaluate(() => {
    if (typeof openLawModal === 'function') {
      try { openLawModal('laws/zakon-pro-hromadianstvo.html'); return true; }
      catch (e) { return 'err:' + e.message; }
    }
    return false;
  });
  check('openLawModal викликано', lawOpened === true);
  await page.waitForTimeout(2500);
  await page.screenshot({ path: path.join(OUT_DIR, 'v2_03_law_modal.png'), fullPage: false });
  log('Скріншот: v2_03_law_modal.png');

  const lawInfo = await page.evaluate(() => {
    const iframe = document.querySelector('#lawModal iframe, .law-modal iframe, iframe[src*="laws"]');
    if (!iframe) return { error: 'iframe не знайдено' };
    try {
      const doc = iframe.contentDocument;
      const text = doc.body ? doc.body.innerText : '';
      const header = doc.querySelector('.law-header');
      const headerStyle = header ? (header.getAttribute('style') || '') : '';
      return {
        title: doc.title || '',
        hasLawHeader: !!doc.querySelector('.law-header'),
        hasLawContent: !!doc.querySelector('.law-content'),
        articleCount: doc.querySelectorAll('.law-article').length,
        articleTitleCount: doc.querySelectorAll('.law-article-title').length,
        stickyHeader: /position\s*:\s*sticky/.test(headerStyle),
        hasTocBtn: /Зміст/.test(text),
        hasSearchField: /Пошук у законі/.test(text),
        pCount: doc.querySelectorAll('p').length,
        textLen: text.length,
      };
    } catch (e) {
      return { error: 'cross-origin: ' + e.message };
    }
  });
  log('Інфо закону в iframe: ' + JSON.stringify(lawInfo));
  if (lawInfo.error) {
    check('Закон відкрито (iframe доступний)', false);
  } else {
    check('Є .law-header', lawInfo.hasLawHeader);
    check('Є .law-content', lawInfo.hasLawContent);
    check(`Статей (.law-article): ${lawInfo.articleCount}`, lawInfo.articleCount > 0);
    check(`Заголовків статей (.law-article-title): ${lawInfo.articleTitleCount}`, lawInfo.articleTitleCount > 0);
    check('Шапка sticky (position:sticky)', lawInfo.stickyHeader);
    check('Є кнопка «Зміст»', lawInfo.hasTocBtn);
    check('Є поле «Пошук у законі»', lawInfo.hasSearchField);
    check(`Абзаців <p>: ${lawInfo.pCount}`, lawInfo.pCount > 0);
  }

  // ---------- 4. Перевірка типографіки (ст. 178 № 429) ----------
  log('\n=== 4. Типографіка (ст. 178 № 429) ===');
  const typo = await page.evaluate(() => {
    const iframe = document.querySelector('#lawModal iframe, .law-modal iframe, iframe[src*="laws"]');
    if (!iframe) return { error: 'iframe не знайдено' };
    try {
      const doc = iframe.contentDocument;
      const text = doc.body ? doc.body.innerText : '';
      return {
        hasBadNoSpace: /ст\.\d|№\d|п\.\d|ч\.\d/.test(text),   // погано: без пробілу
        hasGoodSpace: /ст\. \d|№ \d|п\. \d|ч\. \d/.test(text), // добре: з пробілом
      };
    } catch (e) { return { error: e.message }; }
  });
  log('Типографіка: ' + JSON.stringify(typo));
  if (!typo.error) {
    check('Немає злитих «ст.178№429» (без пробілів)', !typo.hasBadNoSpace);
    check('Є коректні «ст. 178 № 429» (з пробілами)', typo.hasGoodSpace);
  }

  // ---------- 5. Скріншот iframe закону (повний документ) ----------
  try {
    const iframeLoc = page.locator('#lawModal iframe, .law-modal iframe, iframe[src*="laws"]').first();
    if (await iframeLoc.count() > 0) {
      await iframeLoc.screenshot({ path: path.join(OUT_DIR, 'v2_04_law_iframe_full.png') });
      log('Скріншот: v2_04_law_iframe_full.png (iframe закону)');
    }
  } catch (e) {
    log('Не вдалося зробити скріншот iframe: ' + e.message);
  }

  await browser.close();

  log('\n=== ПІДСУМОК ВІЗУАЛЬНОГО АУДИТУ v2 ===');
  log(`Пройдено: ${pass} | Провалено: ${fail}`);
  log(`Результат: ${fail === 0 ? '✅ ВСІ ПЕРЕВІРКИ ПРОЙДЕНО' : '❌ Є ПРОВАЛЕНІ ПЕРЕВІРКИ'}`);
  fs.writeFileSync(path.join(OUT_DIR, '_audit_summary_v2.txt'), results.join('\n'));
  console.log('\nГотово. Скріншоти в ' + OUT_DIR);
})().catch(e => {
  console.error('ПОМИЛКА:', e);
  process.exit(1);
});
