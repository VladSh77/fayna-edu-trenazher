#!/usr/bin/env node
/* screenshot_audit.js
 * Візуальний аудит: робить реальні скріншоти оновлених сторінок
 * (головна, список тем банку МЗС, модальне вікно закону «Регламент ВР»).
 * Використовує Playwright + локальний HTTP-сервер на :8080.
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = 'http://localhost:8080';
const OUT_DIR = path.join(__dirname, '..', 'screenshots');
const results = [];

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
  await page.screenshot({ path: path.join(OUT_DIR, '01_home.png'), fullPage: false });
  log('Скріншот: 01_home.png');

  const homeText = await page.evaluate(() => document.body.innerText);
  const homeHasLibrary = /Бібліотека законів/.test(homeText);
  const homeHasHowTo = /Як користуватися/.test(homeText);
  log(`Головна містить «Бібліотека законів»: ${homeHasLibrary} (має бути false)`);
  log(`Головна містить «Як користуватися»: ${homeHasHowTo} (має бути false)`);
  const bankCards = await page.evaluate(() => document.querySelectorAll('[data-bank]').length);
  log(`Карток банків на головній: ${bankCards}`);

  // ---------- 2. Відкрити банк МЗС (список тем) ----------
  log('\n=== 2. Банк МЗС — список тем ===');
  const clicked = await page.evaluate(() => {
    const cards = Array.from(document.querySelectorAll('[data-bank]'));
    const target = cards.find(el => /МЗС|міністерство|зовнішніх справ|віцеконсул/i.test(el.innerText || ''));
    if (target) { target.click(); return true; }
    return false;
  });
  log(`Клік по банку МЗС: ${clicked}`);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(OUT_DIR, '02_bank_topics.png'), fullPage: false });
  log('Скріншот: 02_bank_topics.png');

  const topicsInfo = await page.evaluate(() => {
    const text = document.body.innerText;
    return {
      hasProgressBlock: /Прогрес по темах/.test(text),
      hasQuickActions: /Обрати всі|Зняти всі|Тільки з помилками/.test(text),
      hasStickyBar: /Навчатися за обраними темами/.test(text),
      hasSearch: /Пошук теми/.test(text),
      topicRows: document.querySelectorAll('.topic-row').length,
      hasLawLib: /Бібліотека законів/.test(text),
    };
  });
  log(`Окремий блок «Прогрес по темах»: ${topicsInfo.hasProgressBlock} (має бути false)`);
  log(`Quick Actions Toolbar: ${topicsInfo.hasQuickActions}`);
  log(`Sticky Action Bar: ${topicsInfo.hasStickyBar}`);
  log(`Пошук тем: ${topicsInfo.hasSearch}`);
  log(`Рядків тем (.topic-row): ${topicsInfo.topicRows}`);
  log(`«Бібліотека законів» всередині банку: ${topicsInfo.hasLawLib}`);

  // Перевірка єдиної картки теми: чекбокс + заголовок + прогрес + скидання в одному рядку
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

  // ---------- 3. Модальне вікно закону «Регламент ВР» ----------
  log('\n=== 3. Модальне вікно закону «Регламент ВР» ===');
  const lawOpened = await page.evaluate(() => {
    if (typeof openLawModal === 'function') {
      try { openLawModal('laws/rehlament-verkhovnoi-rady.html'); return true; }
      catch (e) { return 'err:' + e.message; }
    }
    return false;
  });
  log(`openLawModal викликано: ${lawOpened}`);
  await page.waitForTimeout(2500);
  await page.screenshot({ path: path.join(OUT_DIR, '03_law_modal.png'), fullPage: false });
  log('Скріншот: 03_law_modal.png');

  const lawInfo = await page.evaluate(() => {
    const iframe = document.querySelector('#lawModal iframe, .law-modal iframe, iframe[src*="laws"]');
    if (!iframe) return { error: 'iframe не знайдено' };
    try {
      const doc = iframe.contentDocument;
      const text = doc.body ? doc.body.innerText : '';
      return {
        title: doc.title || '',
        hasStickyHeader: !!doc.querySelector('.law-header, .doc-header'),
        pCount: doc.querySelectorAll('p').length,
        h3Count: doc.querySelectorAll('h3').length,
        hasAmendments: !!doc.querySelector('details.law-amendments'),
        textLen: text.length,
      };
    } catch (e) {
      return { error: 'cross-origin: ' + e.message };
    }
  });
  log('Інфо закону в iframe: ' + JSON.stringify(lawInfo));

  // Скріншот iframe окремо (повний документ) через locator
  try {
    const iframeLoc = page.locator('#lawModal iframe, .law-modal iframe, iframe[src*="laws"]').first();
    if (await iframeLoc.count() > 0) {
      await iframeLoc.screenshot({ path: path.join(OUT_DIR, '04_law_iframe_full.png') });
      log('Скріншот: 04_law_iframe_full.png (iframe закону)');
    }
  } catch (e) {
    log('Не вдалося зробити скріншот iframe: ' + e.message);
  }

  await browser.close();

  log('\n=== ПІДСУМОК ВІЗУАЛЬНОГО АУДИТУ ===');
  log('Скріншоти збережено в: ' + OUT_DIR);
  fs.writeFileSync(path.join(OUT_DIR, '_audit_summary.txt'), results.join('\n'));
  console.log('\nГотово. Скріншоти в ' + OUT_DIR);
})().catch(e => {
  console.error('ПОМИЛКА:', e);
  process.exit(1);
});
