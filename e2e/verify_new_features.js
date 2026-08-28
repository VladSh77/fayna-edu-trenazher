// Швидка перевірка нових фіч: Бібліотека законів, TOC, кнопка «вгору», форматування
const { chromium } = require('playwright');

const BASE = 'http://localhost:8080/';
const results = [];
function check(name, ok, detail) {
  results.push({ name, ok, detail });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ' — ' + detail : ''}`);
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } }); // mobile
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  await page.goto(BASE, { waitUntil: 'networkidle' });

  // 1. Головна — кнопка «Бібліотека законів»
  const lawLibBtn = await page.locator('[data-action="lawlib"]').count();
  check('Кнопка «Бібліотека законів» на головній', lawLibBtn === 1, `знайдено ${lawLibBtn}`);

  // 2. Відкрити бібліотеку
  await page.locator('[data-action="lawlib"]').click();
  await page.waitForSelector('#lawLibList');
  const lawItems = await page.locator('.law-item').count();
  check('Бібліотека: список актів', lawItems > 40, `актів: ${lawItems}`);

  // 3. Пошук
  await page.fill('#lawLibSearch', 'нотаріат');
  await page.waitForTimeout(200);
  const searchItems = await page.locator('.law-item').count();
  check('Бібліотека: пошук «нотаріат»', searchItems >= 1, `знайдено: ${searchItems}`);

  // 4. Відкрити закон про нотаріат
  await page.locator('.law-item').first().click();
  await page.waitForSelector('#lawModal:not(.hidden)');
  await page.waitForSelector('#lawModalBody iframe');
  await page.waitForTimeout(1500); // чекаємо завантаження iframe + TOC
  check('Модальне вікно закону відкрилось', true);

  // 5. TOC побудовано
  const tocLinks = await page.locator('#lawToc a').count();
  check('TOC (зміст) побудовано', tocLinks > 5, `пунктів змісту: ${tocLinks}`);

  // 6. Кнопка «Зміст» перемикає TOC
  const tocVisibleBefore = await page.locator('#lawToc.open').count();
  await page.locator('#lawTocToggle').click();
  const tocVisibleAfter = await page.locator('#lawToc.open').count();
  check('Кнопка «☰ Зміст» перемикає TOC', tocVisibleBefore !== tocVisibleAfter, `до:${tocVisibleBefore} після:${tocVisibleAfter}`);
  await page.locator('#lawTocToggle').click(); // закрити назад

  // 7. Кнопка «↑ Вгору» існує і клікабельна
  const scrollTopBtn = await page.locator('#lawScrollTop').count();
  check('Кнопка «↑ Вгору» в тулбарі', scrollTopBtn === 1);

  // 8. Форматування: у iframe є стилі (h3 з фоном)
  const iframeDoc = await page.locator('#lawModalBody iframe').evaluateHandle(f => f.contentDocument);
  const h3Count = await iframeDoc.evaluate(d => d.querySelectorAll('.doc-body h3').length);
  check('Форматування: у документі є статті (h3)', h3Count > 5, `статей: ${h3Count}`);

  // 9. Закрити модальне
  await page.locator('#lawModalClose').click();
  await page.waitForTimeout(300);
  const modalHidden = await page.locator('#lawModal.hidden').count();
  check('Модальне вікно закривається', modalHidden === 1);

  // 10. Повернення назад до головної
  await page.locator('#lawLibBack').click();
  await page.waitForTimeout(300);
  const backHome = await page.locator('[data-action="lawlib"]').count();
  check('Повернення «← Назад» до головної', backHome === 1);

  // 11. JS-помилки
  check('Немає JS-помилок', errors.length === 0, errors.length ? errors.join(' | ') : '');

  await browser.close();

  const passed = results.filter(r => r.ok).length;
  console.log(`\n=== ПІДСУМОК: ${passed}/${results.length} перевірок пройдено ===`);
  process.exit(passed === results.length ? 0 : 1);
})().catch(e => { console.error('FATAL:', e); process.exit(1); });
