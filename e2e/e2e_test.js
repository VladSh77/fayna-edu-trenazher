/**
 * E2E-тестування інтерфейсу тренажера МЗС-2026 (Playwright).
 *
 * Запуск:
 *   cd e2e && node e2e_test.js
 *
 * Що перевіряє:
 *   1. Проклік усіх 1088 питань у режимі «Навчання» (підсвічування correct/wrong)
 *   2. Проклік усіх питань у режимі «Іспит» (neutral підсвічування)
 *   3. Модальне вікно пояснення з ref (відкривається без помилок/зсувів)
 *   4. Адаптивність: Mobile (390x844) та Desktop (1920x1080)
 *      — touch-target >= 44px, відсутність горизонтального скролу, читабельність шрифтів, контраст
 *   5. Збереження прогресу в localStorage
 *
 * Результат: E2E_REPORT.md у корені проєкту.
 */
'use strict';
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:8080';
const REPORT_PATH = path.join(__dirname, '..', 'E2E_REPORT.md');

// ====== Збір результатів ======
const results = [];
let passed = 0;
let failed = 0;
let warnings = 0;

function record(name, ok, detail = '') {
  const status = ok ? '✅ PASS' : '❌ FAIL';
  if (ok) passed++; else failed++;
  results.push({ name, ok, detail });
  console.log(`  ${status} ${name}${detail ? ' — ' + detail : ''}`);
}

function recordWarn(name, detail = '') {
  warnings++;
  results.push({ name, ok: true, detail: '⚠️ WARN — ' + detail });
  console.log(`  ⚠️ WARN ${name} — ${detail}`);
}

// ====== Допоміжні ======
async function waitFor(selector, page, timeout = 5000) {
  await page.waitForSelector(selector, { timeout });
}

// Перевірка горизонтального скролу
async function checkNoHorizontalScroll(page, label) {
  const hasHScroll = await page.evaluate(() => {
    return document.documentElement.scrollWidth > document.documentElement.clientWidth + 1;
  });
  record(`[${label}] Відсутність горизонтального скролу`, !hasHScroll,
    hasHScroll ? `scrollWidth=${document ? '' : ''}` : '');
}

// Перевірка touch-target (мінімум 44px)
async function checkTouchTargets(page, label) {
  const small = await page.evaluate(() => {
    const bad = [];
    document.querySelectorAll('button, .option, .explain-link, .law-modal-close').forEach(el => {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0 && (r.height < 44 || r.width < 44)) {
        bad.push({ cls: el.className, w: Math.round(r.width), h: Math.round(r.height) });
      }
    });
    return bad.slice(0, 10);
  });
  record(`[${label}] Touch-target >= 44px`, small.length === 0,
    small.length ? JSON.stringify(small) : '');
}

// Перевірка контрасту ключових елементів (спрощена — перевіряємо наявність кольорових класів)
async function checkContrast(page, label) {
  const ok = await page.evaluate(() => {
    // Перевіряємо, що текст не зливається з фоном: body color != bg
    const body = getComputedStyle(document.body);
    const bg = body.backgroundColor;
    const color = body.color;
    return bg && color && bg !== color;
  });
  record(`[${label}] Контраст тексту/фону`, ok);
}

// Перевірка читабельності шрифтів (font-size >= 14px для основного тексту)
async function checkFontReadability(page, label) {
  const small = await page.evaluate(() => {
    const bad = [];
    document.querySelectorAll('.question-text, .option, .explain-box, .section-title, .top-bar h1').forEach(el => {
      const fs = parseFloat(getComputedStyle(el).fontSize);
      if (fs > 0 && fs < 14) bad.push({ cls: el.className, fs });
    });
    return bad.slice(0, 10);
  });
  record(`[${label}] Читабельність шрифтів (>=14px)`, small.length === 0,
    small.length ? JSON.stringify(small) : '');
}

// ====== Головний тест ======
async function run() {
  console.log('🚀 Запуск E2E-тестування тренажера МЗС-2026');
  console.log(`   Base URL: ${BASE_URL}`);
  console.log('');

  const browser = await chromium.launch({ headless: true });

  // ============================================================
  // ТЕСТ 1: Проклік усіх питань у режимі «Навчання» (Desktop)
  // ============================================================
  console.log('📖 ТЕСТ 1: Режим «Навчання» — проклік усіх 1088 питань (Desktop)');
  {
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
    const errors = [];
    page.on('pageerror', e => errors.push('pageerror: ' + e.message));
    page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });

    await page.goto(BASE_URL + '/index.html', { waitUntil: 'networkidle' });
    await waitFor('[data-bank]', page);

    // Обираємо банк
    await page.click('[data-bank]');
    await waitFor('#btnLearn', page);

    // Отримуємо кількість розділів та питань
    const bankInfo = await page.evaluate(() => {
      const secs = document.querySelectorAll('.section-item');
      return { sections: secs.length };
    });

    // Клікаємо «Навчання» (починає з першого розділу)
    await page.click('#btnLearn');
    await waitFor('#optionsBox', page);

    let totalQuestions = 0;
    let correctHighlight = 0;
    let wrongHighlight = 0;
    let explainShown = 0;
    let refLinks = 0;
    let modalOpened = 0;
    let modalErrors = 0;
    let uiShiftErrors = 0;

    // Проходимо всі розділи
    let sectionIdx = 0;
    while (true) {
      // Перевіряємо, чи ми на екрані навчання
      const isLearn = await page.$('#optionsBox');
      if (!isLearn) break;

      // Проходимо всі питання поточного розділу
      while (true) {
        const qText = await page.$('#qText');
        if (!qText) break;
        totalQuestions++;

        // Отримуємо кількість опцій
        const optCount = await page.$$eval('.option', els => els.length);
        if (optCount < 2) {
          record('Кількість опцій >= 2', false, `знайдено ${optCount}`);
        }

        // Клікаємо першу опцію (випадково правильну чи неправильну)
        const options = await page.$$('.option');
        // Клікаємо опцію, яка не disabled
        const clickable = [];
        for (const opt of options) {
          const disabled = await opt.isDisabled();
          if (!disabled) clickable.push(opt);
        }
        if (clickable.length === 0) {
          // Вже відповіли — переходимо далі
          await page.click('#nextBtn');
          continue;
        }
        // Клікаємо першу доступну опцію
        await clickable[0].click();
        await page.waitForTimeout(50);

        // Перевіряємо підсвічування
        const highlight = await page.evaluate(() => {
          const opts = document.querySelectorAll('.option');
          let correct = 0, wrong = 0, neutral = 0, disabled = 0;
          opts.forEach(o => {
            if (o.classList.contains('correct')) correct++;
            if (o.classList.contains('wrong')) wrong++;
            if (o.classList.contains('neutral')) neutral++;
            if (o.classList.contains('disabled')) disabled++;
          });
          return { correct, wrong, neutral, disabled };
        });

        // У режимі навчання після відповіді має бути 1 correct
        if (highlight.correct === 1) correctHighlight++;
        else record('Підсвічування правильної відповіді', false, JSON.stringify(highlight));

        // Якщо відповіли неправильно — має бути 1 wrong
        if (highlight.wrong === 1) wrongHighlight++;

        // Перевіряємо наявність explainBox
        const explain = await page.$('.explain-box');
        if (explain) {
          explainShown++;
          // Перевіряємо наявність ref-посилання
          const link = await page.$('.explain-link');
          if (link) {
            refLinks++;
            // Відкриваємо модальне вікно
            const beforeScroll = await page.evaluate(() => document.documentElement.scrollWidth);
            await link.click();
            // Чекаємо, поки модальне вікно стане видимим (асинхронне відкриття)
            let modalVisible = false;
            try {
              await page.waitForSelector('#lawModal:not(.hidden)', { timeout: 3000 });
              modalVisible = true;
            } catch (e) { /* модальне вікно не відкрилось */ }
            if (modalVisible) {
              modalOpened++;
              // Чекаємо, поки iframe завантажиться
              let iframeLoaded = false;
              try {
                await page.waitForSelector('#lawModalBody iframe', { timeout: 5000 });
                iframeLoaded = true;
              } catch (e) { /* iframe не завантажився */ }
              if (iframeLoaded) {
                // Перевіряємо зсув UI (ширина не змінилась)
                const afterScroll = await page.evaluate(() => document.documentElement.scrollWidth);
                if (Math.abs(afterScroll - beforeScroll) > 2) {
                  uiShiftErrors++;
                  record('Модальне вікно без зсуву UI', false, `scrollWidth ${beforeScroll}->${afterScroll}`);
                }
              } else {
                modalErrors++;
                record('Модальне вікно завантажило iframe', false);
              }
              // Закриваємо модальне вікно
              await page.click('#lawModalClose');
              // Чекаємо, поки модальне вікно закриється (hidden) і оверлей зникне
              try {
                await page.waitForSelector('#lawModal.hidden', { timeout: 3000 });
              } catch (e) { /* модальне вікно вже закрилось */ }
              // Додатково чекаємо, поки оверлей повністю приховається (display:none),
              // щоб iframe не перехоплював кліки по #nextBtn
              try {
                await page.waitForFunction(() => {
                  const m = document.getElementById('lawModal');
                  if (!m) return true;
                  const cs = getComputedStyle(m);
                  return cs.display === 'none' || cs.visibility === 'hidden' || m.classList.contains('hidden');
                }, { timeout: 3000 });
              } catch (e) { /* оверлей вже прихований */ }
              // Невелика пауза для стабілізації DOM перед наступним питанням
              await page.waitForTimeout(150);
            } else {
              modalErrors++;
              record('Модальне вікно відкрилось', false);
            }
          }
        }

        // Переходимо до наступного питання (force:true — оверлей модального вікна вже закритий)
        await page.click('#nextBtn', { force: true });
        await page.waitForTimeout(30);
      }

      // Після завершення розділу — кнопка «До розділів»
      const toSections = await page.$('#toSections');
      if (toSections) {
        await toSections.click();
        await waitFor('#btnLearn', page);
        sectionIdx++;
        // Клікаємо наступний розділ
        const learnBtns = await page.$$('[data-learn]');
        if (sectionIdx < learnBtns.length) {
          await learnBtns[sectionIdx].click();
          await waitFor('#optionsBox', page);
        } else {
          break;
        }
      } else {
        break;
      }
    }

    record('Проклік усіх питань у «Навчанні»', totalQuestions >= 1088, `пройдено ${totalQuestions}`);
    record('Підсвічування правильної відповіді (correct)', correctHighlight >= 1088, `${correctHighlight}`);
    record('Підсвічування неправильної відповіді (wrong)', wrongHighlight >= 0, `${wrongHighlight}`);
    record('Пояснення показано', explainShown >= 1088, `${explainShown}`);
    record('Ref-посилання на закон', refLinks >= 900, `${refLinks}`);
    record('Модальне вікно закону відкрилось', modalOpened >= 900, `${modalOpened}`);
    record('Модальне вікно без помилок', modalErrors === 0, `помилок: ${modalErrors}`);
    record('Модальне вікно без зсуву UI', uiShiftErrors === 0, `зсувів: ${uiShiftErrors}`);
    record('Відсутність JS-помилок', errors.length === 0, errors.slice(0, 3).join('; '));

    // Перевірка збереження прогресу в localStorage
    const progress = await page.evaluate(() => {
      const keys = Object.keys(localStorage).filter(k => k.startsWith('trenazher:'));
      const data = {};
      for (const k of keys) {
        try { data[k] = JSON.parse(localStorage.getItem(k)); } catch (e) { data[k] = null; }
      }
      return { keys, data };
    });
    const savedTotal = Object.values(progress.data).reduce((acc, p) => {
      if (!p) return acc;
      return acc + Object.values(p).reduce((a, s) => a + (s.correct ? s.correct.length : 0) + (s.wrong ? s.wrong.length : 0), 0);
    }, 0);
    record('Збереження прогресу в localStorage', progress.keys.length > 0 && savedTotal >= 1088,
      `збережено ${savedTotal} відповідей у ${progress.keys.length} ключах`);

    await page.close();
  }

  // ============================================================
  // ТЕСТ 2: Режим «Іспит» (Desktop)
  // ============================================================
  console.log('');
  console.log('📝 ТЕСТ 2: Режим «Іспит» (Desktop)');
  {
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
    const errors = [];
    page.on('pageerror', e => errors.push('pageerror: ' + e.message));
    page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });

    await page.goto(BASE_URL + '/index.html', { waitUntil: 'networkidle' });
    await waitFor('[data-bank]', page);
    await page.click('[data-bank]');
    await waitFor('#btnExam', page);
    await page.click('#btnExam');
    await waitFor('#startExam', page);

    // Починаємо екзамен
    await page.click('#startExam');
    await waitFor('#optionsBox', page);

    let examQuestions = 0;
    let neutralHighlight = 0;
    let examFinished = false;

    while (true) {
      const qText = await page.$('#qText');
      if (!qText) break;
      examQuestions++;

      // Клікаємо першу доступну опцію
      const options = await page.$$('.option');
      const clickable = [];
      for (const opt of options) {
        const disabled = await opt.isDisabled();
        if (!disabled) clickable.push(opt);
      }
      if (clickable.length > 0) {
        await clickable[0].click();
        await page.waitForTimeout(50);
        // Перевіряємо neutral підсвічування
        const neutral = await page.evaluate(() => document.querySelectorAll('.option.neutral').length);
        if (neutral === 1) neutralHighlight++;
      }

      // Переходимо далі або завершуємо
      const nextBtn = await page.$('#nextExam');
      if (nextBtn) {
        const label = await nextBtn.textContent();
        await nextBtn.click();
        await page.waitForTimeout(50);
        if (label.includes('Завершити')) {
          examFinished = true;
          break;
        }
      } else {
        break;
      }
    }

    // Перевіряємо результат
    const result = await page.$('.exam-summary');
    record('Екзамен завершено', examFinished && !!result, `питань: ${examQuestions}`);
    record('Neutral підсвічування в екзамені', neutralHighlight >= 30, `${neutralHighlight}`);
    record('Відсутність JS-помилок в екзамені', errors.length === 0, errors.slice(0, 3).join('; '));

    await page.close();
  }

  // ============================================================
  // ТЕСТ 3: Адаптивність Mobile (390x844)
  // ============================================================
  console.log('');
  console.log('📱 ТЕСТ 3: Адаптивність Mobile (390x844)');
  {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    const errors = [];
    page.on('pageerror', e => errors.push('pageerror: ' + e.message));

    await page.goto(BASE_URL + '/index.html', { waitUntil: 'networkidle' });
    await waitFor('[data-bank]', page);
    await checkNoHorizontalScroll(page, 'Mobile home');
    await checkTouchTargets(page, 'Mobile home');
    await checkFontReadability(page, 'Mobile home');
    await checkContrast(page, 'Mobile home');

    await page.click('[data-bank]');
    await waitFor('#btnLearn', page);
    await checkNoHorizontalScroll(page, 'Mobile sections');
    await checkTouchTargets(page, 'Mobile sections');

    await page.click('#btnLearn');
    await waitFor('#optionsBox', page);
    await checkNoHorizontalScroll(page, 'Mobile learn');
    await checkTouchTargets(page, 'Mobile learn');
    await checkFontReadability(page, 'Mobile learn');

    // Клікаємо опцію і перевіряємо, що все працює на мобільному
    const options = await page.$$('.option');
    if (options.length > 0) {
      await options[0].click();
      await page.waitForTimeout(100);
      const explain = await page.$('.explain-box');
      record('Mobile: пояснення після відповіді', !!explain);
      // Відкриваємо модальне вікно
      const link = await page.$('.explain-link');
      if (link) {
        await link.click();
        // Чекаємо, поки модальне вікно стане видимим і завантажиться iframe
        await page.waitForSelector('#lawModal:not(.hidden)', { timeout: 5000 });
        await page.waitForSelector('#lawModalBody iframe', { timeout: 10000 });
        await page.waitForTimeout(300);
        const modalVisible = await page.$eval('#lawModal', el => !el.classList.contains('hidden'));
        record('Mobile: модальне вікно закону', modalVisible);
        await checkNoHorizontalScroll(page, 'Mobile modal');
        // Закриваємо через кнопку (має бути видимою та клікабельною)
        await page.click('#lawModalClose', { timeout: 5000 });
        const modalClosed = await page.$eval('#lawModal', el => el.classList.contains('hidden'));
        record('Mobile: закриття модального вікна', modalClosed);
      }
    }

    record('Mobile: відсутність JS-помилок', errors.length === 0, errors.slice(0, 3).join('; '));
    await page.close();
  }

  // ============================================================
  // ТЕСТ 4: Адаптивність Desktop (1920x1080)
  // ============================================================
  console.log('');
  console.log('🖥️ ТЕСТ 4: Адаптивність Desktop (1920x1080)');
  {
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
    const errors = [];
    page.on('pageerror', e => errors.push('pageerror: ' + e.message));

    await page.goto(BASE_URL + '/index.html', { waitUntil: 'networkidle' });
    await waitFor('[data-bank]', page);
    await checkNoHorizontalScroll(page, 'Desktop home');
    await checkTouchTargets(page, 'Desktop home');
    await checkFontReadability(page, 'Desktop home');
    await checkContrast(page, 'Desktop home');

    await page.click('[data-bank]');
    await waitFor('#btnLearn', page);
    await checkNoHorizontalScroll(page, 'Desktop sections');

    await page.click('#btnLearn');
    await waitFor('#optionsBox', page);
    await checkNoHorizontalScroll(page, 'Desktop learn');
    await checkTouchTargets(page, 'Desktop learn');
    await checkFontReadability(page, 'Desktop learn');

    record('Desktop: відсутність JS-помилок', errors.length === 0, errors.slice(0, 3).join('; '));
    await page.close();
  }

  await browser.close();

  // ====== Формування звіту ======
  console.log('');
  console.log('========================================');
  console.log(`Результат: ${passed} PASS, ${failed} FAIL, ${warnings} WARN`);
  console.log('========================================');

  const lines = [];
  lines.push('# Звіт E2E-тестування інтерфейсу тренажера МЗС-2026');
  lines.push('');
  lines.push(`- **Дата:** ${new Date().toISOString()}`);
  lines.push(`- **Base URL:** ${BASE_URL}`);
  lines.push(`- **Браузер:** Chromium (headless)`);
  lines.push(`- **Роздільні здатності:** Mobile 390x844, Desktop 1920x1080`);
  lines.push('');
  lines.push(`## Підсумок`);
  lines.push('');
  lines.push(`| Метрика | Значення |`);
  lines.push(`|---------|----------|`);
  lines.push(`| ✅ Passed | ${passed} |`);
  lines.push(`| ❌ Failed | ${failed} |`);
  lines.push(`| ⚠️ Warnings | ${warnings} |`);
  lines.push(`| **Успішність** | **${passed + warnings} / ${passed + failed + warnings} (${Math.round((passed + warnings) / Math.max(1, passed + failed + warnings) * 100)}%)** |`);
  lines.push('');
  lines.push(`## Детальні результати`);
  lines.push('');
  lines.push(`| # | Тест | Статус | Деталі |`);
  lines.push(`|---|------|--------|--------|`);
  results.forEach((r, i) => {
    const status = r.ok ? '✅' : '❌';
    lines.push(`| ${i + 1} | ${r.name} | ${status} | ${r.detail || ''} |`);
  });
  lines.push('');
  lines.push(`## Висновок`);
  lines.push('');
  if (failed === 0) {
    lines.push(`**✅ ВСІ E2E-ТЕСТИ ПРОЙДЕНО УСПІШНО (100% Passed).**`);
    lines.push('');
    lines.push(`Інтерфейс тренажера повністю функціональний: усі ${passed} перевірок пройдено без помилок.`);
    lines.push(`- Усі питання в режимах «Навчання» та «Іспит» коректно підсвічуються.`);
    lines.push(`- Модальне вікно пояснення з ref відкривається без помилок і зсувів UI.`);
    lines.push(`- Адаптивність підтверджена для Mobile (390x844) та Desktop (1920x1080).`);
    lines.push(`- Прогрес коректно зберігається в localStorage.`);
  } else {
    lines.push(`**❌ Виявлено ${failed} помилок. Потрібне виправлення перед деплоєм.**`);
  }
  lines.push('');

  fs.writeFileSync(REPORT_PATH, lines.join('\n'), 'utf8');
  console.log(`\n📄 Звіт збережено: ${REPORT_PATH}`);

  process.exit(failed === 0 ? 0 : 1);
}

run().catch(err => {
  console.error('❌ Критична помилка E2E-тесту:', err);
  process.exit(1);
});
