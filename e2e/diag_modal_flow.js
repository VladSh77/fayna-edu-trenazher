/**
 * Діагностика: чому модальне вікно не відкривається в E2E-тесті.
 * Відтворює точний флоу тесту: клік першої опції -> клік .explain-link -> перевірка #lawModal.
 * Ловить JS-помилки та друкує стан DOM.
 */
'use strict';
const { chromium } = require('playwright');

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:8080';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });

  const errors = [];
  page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('CONSOLE: ' + m.text()); });

  await page.goto(BASE_URL + '/index.html', { waitUntil: 'networkidle' });
  await page.waitForSelector('[data-bank]');

  // Обираємо банк
  await page.click('[data-bank]');
  await page.waitForSelector('#btnLearn');

  // Клікаємо «Навчання»
  await page.click('#btnLearn');
  await page.waitForSelector('#optionsBox');

  // Клікаємо першу доступну опцію
  const options = await page.$$('.option');
  const clickable = [];
  for (const opt of options) {
    const disabled = await opt.isDisabled();
    if (!disabled) clickable.push(opt);
  }
  console.log('Знайдено опцій:', options.length, 'клікабельних:', clickable.length);
  await clickable[0].click();
  await page.waitForTimeout(200);

  // Перевіряємо explain-box та explain-link
  const explainBox = await page.$('.explain-box');
  console.log('explain-box присутній:', !!explainBox);
  const link = await page.$('.explain-link');
  console.log('explain-link присутній:', !!link);

  if (link) {
    // Перевіряємо, чи є onclick у елемента
    const hasOnclick = await page.evaluate(() => {
      const el = document.querySelector('.explain-link');
      return { hasOnclick: typeof el.onclick === 'function', dataLaw: el.getAttribute('data-law') };
    });
    console.log('onclick стан:', JSON.stringify(hasOnclick));

    // Клікаємо
    await link.click();
    await page.waitForTimeout(500);

    // Перевіряємо модальне вікно
    const modalState = await page.evaluate(() => {
      const m = document.getElementById('lawModal');
      if (!m) return { exists: false };
      return {
        exists: true,
        hidden: m.classList.contains('hidden'),
        display: getComputedStyle(m).display,
        bodyHtml: document.getElementById('lawModalBody').innerHTML.slice(0, 200)
      };
    });
    console.log('Модальне вікно стан:', JSON.stringify(modalState, null, 2));
  }

  console.log('\n=== JS-помилки ===');
  if (errors.length === 0) console.log('(немає)');
  else errors.forEach(e => console.log(e));

  await browser.close();
})();
