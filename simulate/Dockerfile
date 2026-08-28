# Повна перевірочна симуляція всієї бази питань МЗС (1088 питань / 37 розділів) у Docker.
#
# Запускає run_full_simulation.py, який:
#   1) завантажує повну базу питань (banks/mzs-2026.fixed2.json) і закони (laws/*.html);
#   2) для кожного питання перевіряє: чи існує ref, чи збігається текст статті
#      з варіантом correct;
#   3) класифікує помилки: VALID / REF_INVALID / TEXT_MISMATCH / MISSING_LAW;
#   4) підтримує батчинг (по N питань або по 37 розділах) із збереженням
#      проміжних логів у simulation_results.json;
#   5) генерує підсумковий звіт проходження у %.
#
# Жодних зовнішніх залежностей — тільки стандартна бібліотека Python.
# Скрипти копіюються в образ як fallback, але при запуску через compose
# корінь проєкту монтується в /app (див. docker-compose.yml), тому
# виконується /app/simulate/run_full_simulation.py з живого volume.
FROM python:3.11-slim

WORKDIR /app

# Копіюємо скрипти як fallback (якщо volume не змонтовано).
COPY simulate.py /app/simulate/simulate.py
COPY run_full_simulation.py /app/simulate/run_full_simulation.py

# Проєкт монтується як volume (див. docker-compose.yml), тому банк і закони
# беруться з /app/banks та /app/laws.
ENTRYPOINT ["python", "-u", "/app/simulate/run_full_simulation.py"]
