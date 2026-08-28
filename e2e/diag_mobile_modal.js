'use strict';
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await page.goto('http://localhost:8080/index.html', { waitUntil: 'networkidle' });
  await page.waitForSelector('[data-bank]');
  await page.click('[data-bank]');
  await page.waitForSelector('#btnLearn');
  await page.click('#btnLearn');
  await page.waitForSelector('#optionsBox');
  const options = await page.$$('.option');
  if (options.length > 0) {
    await options[0].click();
    await page.waitForTimeout(200);
    const link = await page.$('.explain-link');
    if (link) {
      await link.click();
      await page.waitForTimeout(500);
      // Діагностика модального вікна
      const info = await page.evaluate(() => {
        const modal = document.getElementById('lawModal');
        const close = document.getElementById('lawModalClose');
        const header = document.querySelector('.law-modal-header');
        const overlay = document.querySelector('.law-modal-overlay');
        const modalEl = document.querySelector('.law-modal');
        const body = document.getElementById('lawModalBody');
        const r = (el) => {
          if (!el) return null;
          const rect = el.getBoundingClientRect();
          const cs = getComputedStyle(el);
          return { top: Math.round(rect.top), bottom: Math.round(rect.bottom), height: Math.round(rect.height), display: cs.display, visibility: cs.visibility, opacity: cs.opacity, position: cs.position, overflow: cs.overflow };
        };
        return {
          modalHidden: modal.classList.contains('hidden'),
          close: r(close),
          header: r(header),
          overlay: r(overlay),
          modal: r(modalEl),
          body: r(body),
          bodyScrollTop: body ? body.scrollTop : null,
          bodyScrollHeight: body ? body.scrollHeight : null,
          bodyClientHeight: body ? body.clientHeight : null,
          scrollY: window.scrollY,
          docScrollHeight: document.documentElement.scrollHeight,
          docClientHeight: document.documentElement.clientHeight,
        };
      });
      console.log(JSON.stringify(info, null, 2));
    }
  }
  await browser.close();
})();
