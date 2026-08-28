/**
 * Швидкий діагностичний тест: відкриття модального вікна закону «Про нотаріат»
 * та інших великих законів. Перевіряє, чи кнопка реагує і чи завантажується iframe.
 */
'use strict';
const { chromium } = require('playwright');

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:8080';

async function testLawModal(page, lawFile) {
  // Відкриваємо модальне вікно напряму через функцію openLawModal
  const result = await page.evaluate(async (file) => {
    return new Promise((resolve) => {
      // Викликаємо openLawModal (глобальна функція)
      try {
        openLawModal(file);
        // Чекаємо, поки iframe з'явиться або помилка
        const check = () => {
          const body = document.getElementById('lawModalBody');
          const iframe = body.querySelector('iframe');
          const error = body.querySelector('.law-modal-error');
          if (iframe) {
            resolve({ status: 'OK', hasIframe: true, iframeSrcLen: (iframe.srcdoc || '').length });
          } else if (error) {
            resolve({ status: 'ERROR', hasIframe: false, error: error.textContent });
          } else {
            setTimeout(check, 200);
          }
        };
        setTimeout(check, 300);
      } catch (e) {
        resolve({ status: 'EXCEPTION', error: e.message });
      }
    });
  }, lawFile);
  return result;
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });

  await page.goto(BASE_URL + '/index.html', { waitUntil: 'networkidle' });
  await page.waitForSelector('[data-bank]');

  // Тестуємо кілька законів, включно з нотаріатом
  const laws = [
    'laws/zakon-pro-notariat.html',
    'laws/zakon-pro-hromadianstvo.html',
    'laws/tsyvilnyi-kodeks-ukrainy.html',
    'laws/kryminalnyi-kodeks-ukrainy.html',
    'laws/uhoda-pro-asotsiatsiiu-ukraina-yes.html',
  ];

  for (const law of laws) {
    const r = await testLawModal(page, law);
    console.log(`${law}: ${JSON.stringify(r)}`);
    // Закриваємо модальне вікно
    await page.evaluate(() => closeLawModal());
    await page.waitForTimeout(200);
  }

  console.log('JS errors:', errors.length ? errors : 'none');
  await browser.close();
}

run().catch(e => { console.error('FATAL:', e); process.exit(1); });
