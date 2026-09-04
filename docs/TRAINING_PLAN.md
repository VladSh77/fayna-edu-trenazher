# 🎯 Систематичний план навчання — fayna-edu-trenazher

> Мета: підтягнути всі навички за CV, пройти всі куплені курси, систематично за темами.
> Головна сторінка = портал зі списками навчань/тестів. Обираєш що цікавить → починаєш вчитись (як з МЗС).

---

## 1. Архітектура платформи

**Головна сторінка** (`index.html`) — портал-вітрина, де зібрано:

| Блок | Що містить | Джерело |
|------|-----------|---------|
| **Тести (банки питань)** | МЗС, IT Administrator, + нові | `banks/*.json` |
| **Курси** | Куплені курси Genius.Space (стubs) | `genius_dump/` |
| **Теми/Стеки** | Технічні теми з Obsidian | `library/tools/` |
| **Золоті стандарти** | Безпека + розробник | `meta/golden-rules-*.md` |

**Реєстр банків** — `banks/manifest.json` (file, title, total, sections).

**Формат банку** — `{title, total, sections: [{id, title, count, questions: [{id, question, correct, wrong[]}]}]}`.

---

## 2. Стек SOFTIQ (вакансія) → систематичні теми

З вакансії **Administrator/Administratorka IT** (SOFTIQ, Gliwice) — обов'язкові теми:

| # | Тема | Статус | Джерело |
|---|------|--------|---------|
| 1 | **Windows & Active Directory** (ADUC, GPO, DNS, DHCP, Kerberos, DSRM) | ✅ 8 питань | `it-admin-interview.json` |
| 2 | **Sieci LAN/WAN/Wi-Fi** (TCP/IP, VLAN, routing, switch, firewall) | ✅ 8 питань | `it-admin-interview.json` |
| 3 | **Microsoft 365 / Exchange / Teams / SharePoint** | ✅ 6 питань | `it-admin-interview.json` |
| 4 | **Backup, bezpieczeństwo, serwery** | ✅ 5 питань | `it-admin-interview.json` |
| 5 | **Scenariusze Help Desk** | ✅ 6 питань | `it-admin-interview.json` |
| 6 | **Linux / serwery** (bash, systemd, SSH, nginx) | ⏳ розширити | Obsidian `linux.md`, `bash.md`, `nginx.md` |
| 7 | **Wirtualizacja** (VMware/Hyper-V/Proxmox) | ⏳ розширити | Obsidian `docker.md`, `kubernetes.md` |
| 8 | **Sieci — pogłębienie** (VPN, DNS, monitoring) | ⏳ розширити | Obsidian `security-basics.md` |
| 9 | **Zarządzanie użytkownikami / polityki** | ⏳ розширити | Obsidian |
| 10 | **Bezpieczeństwo IT** (złote standardy) | ⏳ розширити | `golden-rules-security.md` |

---

## 3. Obsidian технічні теми (104 інструменти, 9 стеків)

**9 стеків** (`library/tools/_stacks/`):

| Стек | Інструменти (приклади) | Навчальний модуль |
|------|------------------------|-------------------|
| **Розробка** | javascript, typescript, react, nodejs, python, php, golang, git, docker | Frontend/Backend |
| **DevOps** | docker, kubernetes, nginx, jenkins, github-actions, linux, bash | CI/CD, інфра |
| **AI-LLM-Агенти** | openai-api, rag, prompt-engineering, claude-code | AI |
| **Маркетинг-SEO** | google-ads, meta-ads, seo, canva | Маркетинг |
| **UX-Дизайн** | figma, photoshop, sketch | Дизайн |
| **Payments** | stripe, wayforpay, przelewy24, sendpulse | Платежі |
| **PKM-Знання** | obsidian, notion, rag, local-rag-mcp | База знань |
| **Продукт-менеджмент** | product-manager-skills | PM |
| **Other** | telegram-bots, n8n, make, zapier | Автоматизація |

---

## 4. Золоті стандарти

- **`golden-rules-security.md`** — ізоляція клієнтів, окремі SSH-ключі, не root, .env, 2FA, аудит
- **`golden-rules-developer.md`** — безпека понад усе, документуй все, сервер тільки через Git, коміт `100`

> Ці стандарти — обов'язковий модуль для IT-адміністратора та розробника.

---

## 5. Куплені курси Genius.Space (15 шт, стubs)

Структуру завантажено у `genius_dump/` (модулі → матеріали). Відео-контент — наступна фаза.

| # | Курс | Модулів | Матеріалів |
|---|------|---------|-----------|
| 1 | AI Спеціаліст | 5 | 38 |
| 2 | HTML/CSS спеціаліст | 19 | 20 |
| 3 | GOOGLE SHEETS 2.0 | 9 | 9 |
| 4 | Комплексний інтернет-маркетинг | 14 | 94 |
| 5 | Професія Графічний дизайнер 2.0 | 5 | 18 |
| 6 | Професія Нутриціолог | 10 | 62 |
| 7 | AI автоматизатор | 10 | 35 |
| 8 | Email-маркетинг | 5 | 13 |
| 9 | Мобільний відеомонтаж 2.0 | 6 | 31 |
| 10 | Бренд-менеджмент, PR та комунікації | 4 | 30 |
| 11 | Професія HR & Recruiting + AI | 8 | 35 |
| 12 | AI Video Creator | 6 | 38 |
| 13 | No-Code Developer | 7 | 39 |
| 14 | Юридична грамотність | 7 | 32 |
| 15 | Професія Дизайнер інтер'єру | 7 | 38 |

**Разом: ~122 модулі, ~570 матеріалів.**

---

## 6. План розширення IT-банку (систематично за темами)

На основі стеку SOFTIQ + Obsidian тем — розширити `it-admin-interview.json`:

1. **Linux / serwery** — bash, systemd, SSH, nginx, права, cron
2. **Wirtualizacja / Docker** — контейнери, образи, volumes, docker-compose
3. **Sieci — pogłębienie** — VPN, DNS, monitoring, VLAN
4. **Bezpieczeństwo IT** — złote standardy, hardening, backup/DR
5. **Zarządzanie / polityki** — użytkownicy, grupy, GPO, audyt

---

## 7. Заглушки для майбутніх курсів

| Курс | Slug | Статус |
|------|------|--------|
| Wychowawca (табір) | `wychowawca` | ⏳ заглушка |
| C++ MilTech | `cpp-miltech` | ⏳ заглушка |
| LLM Engineering | `llm-engineering` | ⏳ заглушка |

---

## 8. Джерела матеріалів

- **Genius.Space** — куплені курси (структура завантажена, відео — наступна фаза)
- **Obsidian** — технічні теми (104 інструменти, 9 стеків)
- **YouTube** — для тем, яких бракує (обираємо кращі матеріали)
- **Золоті стандарти** — безпека + розробник
