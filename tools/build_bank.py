#!/usr/bin/env python3
import json
import re
import sys
from collections import OrderedDict

TRANS = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'h', 'ґ': 'g', 'д': 'd', 'е': 'e',
    'є': 'ie', 'ж': 'zh', 'з': 'z', 'и': 'y', 'і': 'i', 'ї': 'i', 'й': 'i',
    'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
    'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch',
    'ш': 'sh', 'щ': 'shch', 'ю': 'iu', 'я': 'ia', 'ь': ''
}

ABBREVIATIONS = {'МЗС', 'ЄС', 'НАТО', 'США', 'ООН', 'ЦВК', 'МВС', 'РФ', 'СНД', 'ДКС', 'ЗДУ', 'РАЦС', 'ІТ'}

def translit(text):
    text = text.lower()
    result = []
    for ch in text:
        if ch in TRANS:
            result.append(TRANS[ch])
        elif ch.isdigit() or ch == '-':
            result.append(ch)
        elif ch.isalpha():
            result.append(ch)
        else:
            result.append('-')
    slug = re.sub(r'-+', '-', ''.join(result)).strip('-')
    # Cut at word boundary (hyphen)
    if len(slug) > 40:
        cut = slug[:40]
        if '-' in cut:
            cut = cut[:cut.rfind('-')]
        slug = cut
    return slug

def normalize_text(text):
    return re.sub(r'\s+', ' ', text.strip()).lower()

def normalize_block(block):
    text = block
    text = re.sub(r'\s*\(\d+\s+тестових\s+(?:питань|питання)\)\s*$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^Питання та відповіді на перевірку знання\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^[ІIХХV]+\.\s*', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def fix_genitive(title):
    """Convert genitive case to nominative at start of title."""
    patterns = [
        (r'^закону\s+україни', 'Закон України'),
        (r'^віденської\s+конвенції', 'Віденська конвенція'),
        (r'^угоди', 'Угода'),
        (r'^постанови', 'Постанова'),
        (r'^положення', 'Положення'),
        (r'^правил', 'Правила'),
        (r'^наказу', 'Наказ'),
        (r'^інструкції', 'Інструкція'),
    ]
    for pattern, replacement in patterns:
        if re.match(pattern, title, re.IGNORECASE):
            return re.sub(pattern, replacement, title, count=1, flags=re.IGNORECASE)
    return title

def fix_case(word):
    """Convert ALL-CAPS word to Title Case, preserving abbreviations."""
    if word in ABBREVIATIONS:
        return word
    if len(word) > 2 and word.isupper():
        return word[0] + word[1:].lower()
    return word

def fix_title_case(title):
    """Fix case of words in title, preserving abbreviations."""
    # Handle quoted parts
    def fix_quoted(match):
        inner = match.group(1)
        words = inner.split()
        fixed = ' '.join(fix_case(w) for w in words)
        return '«' + fixed + '»'
    
    title = re.sub(r'«([^»]+)»', fix_quoted, title)
    
    # Fix remaining words
    words = title.split()
    fixed_words = []
    for w in words:
        if w.startswith('«') and w.endswith('»'):
            fixed_words.append(w)
        else:
            fixed_words.append(fix_case(w))
    return ' '.join(fixed_words)

def short_title(norm):
    text = re.sub(r'^Питання та відповіді на перевірку знання\s*', '', norm, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    text = fix_genitive(text)
    text = fix_title_case(text)
    if len(text) > 70:
        cut = text[:70]
        if ' ' in cut:
            cut = cut[:cut.rfind(' ')]
        text = cut + '…'
    return text[0].upper() + text[1:] if text else text

def main():
    with open('banks/_raw_mzs.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    questions = data['questions']
    total_in = data.get('total', len(questions))
    print(f"ВХІД: {total_in}")

    # Step 1: filter out Типова інструкція
    filtered = []
    dropped_inst = 0
    for q in questions:
        if 'Типової інструкції про порядок ведення обліку' in q.get('block', ''):
            dropped_inst += 1
        else:
            filtered.append(q)
    print(f"Викинуто «Типова інструкція»: {dropped_inst}")

    # Step 2: group by normalized block
    sections = OrderedDict()
    for q in filtered:
        key = normalize_block(q.get('block', ''))
        if key not in sections:
            sections[key] = []
        sections[key].append(q)

    # Step 3-4: build section metadata
    section_meta = []
    used_ids = set()
    for key, qs in sections.items():
        title = short_title(key)
        base_id = translit(title)
        sid = base_id
        counter = 2
        while sid in used_ids:
            sid = f"{base_id}-{counter}"
            counter += 1
        used_ids.add(sid)
        section_meta.append({'key': key, 'title': title, 'id': sid, 'questions': qs})

    # Step 5: deduplicate questions globally
    seen_questions = set()
    dedup_count = 0
    for meta in section_meta:
        unique_qs = []
        for q in meta['questions']:
            qtext = normalize_text(q.get('question', ''))
            if qtext in seen_questions:
                dedup_count += 1
            else:
                seen_questions.add(qtext)
                unique_qs.append(q)
        meta['questions'] = unique_qs
    print(f"Дублікатів питань: {dedup_count}")

    # Step 6: validation
    stats = {'short': 0, 'empty_correct': 0, 'correct_eq_wrong': 0, 'empty_wrong': 0}
    for meta in section_meta:
        valid_qs = []
        for q in meta['questions']:
            question = q.get('question', '').strip()
            correct = q.get('correct', '').strip()
            wrong = q.get('wrong', [])
            if len(question) < 10:
                stats['short'] += 1
                continue
            if not correct:
                stats['empty_correct'] += 1
                continue
            if not wrong:
                stats['empty_wrong'] += 1
                continue
            wrong_norm = [normalize_text(w) for w in wrong]
            wrong_norm = list(OrderedDict.fromkeys(wrong_norm))
            if normalize_text(correct) in wrong_norm:
                stats['correct_eq_wrong'] += 1
                continue
            if not wrong_norm:
                stats['empty_wrong'] += 1
                continue
            q['wrong'] = wrong_norm
            valid_qs.append(q)
        meta['questions'] = valid_qs
    print(f"Відкинуто валідацією: коротке={stats['short']} порожня_correct={stats['empty_correct']} correct==wrong={stats['correct_eq_wrong']} порожній_wrong={stats['empty_wrong']}")

    # Step 7: sort sections by count descending
    section_meta.sort(key=lambda m: len(m['questions']), reverse=True)

    # Build output
    out_sections = []
    total_out = 0
    for meta in section_meta:
        if not meta['questions']:
            continue
        count = len(meta['questions'])
        total_out += count
        out_sections.append({
            'id': meta['id'],
            'title': meta['title'],
            'count': count,
            'questions': [
                {
                    'id': q.get('id', ''),
                    'question': q['question'],
                    'correct': q['correct'],
                    'wrong': q['wrong']
                }
                for q in meta['questions']
            ]
        })

    bank_data = {
        'title': 'Тести МЗС — віцеконсул 2026',
        'total': total_out,
        'sections': out_sections
    }

    with open('banks/mzs-2026.json', 'w', encoding='utf-8') as f:
        json.dump(bank_data, f, ensure_ascii=False, indent=2)

    manifest = {
        'banks': [
            {
                'file': 'mzs-2026.json',
                'title': 'Тести МЗС — віцеконсул 2026',
                'total': total_out,
                'sections': len(out_sections)
            }
        ]
    }
    with open('banks/manifest.json', 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"СЕКЦІЙ: {len(out_sections)}")
    print(f"ВИХІД: {total_out}")
    print("--- секції ---")
    for sec in out_sections:
        print(f"{sec['count']}  {sec['id']}  {sec['title']}")

    if total_out == 0 or sum(s['count'] for s in out_sections) != total_out:
        print("OK")
        sys.exit(1)
    print("OK")

if __name__ == '__main__':
    main()
