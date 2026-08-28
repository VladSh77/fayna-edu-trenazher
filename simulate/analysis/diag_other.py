import json, re, sys
sys.path.insert(0, 'simulate')
import simulate as S

entries = json.load(open('simulate/analysis/remaining_173.json'))
def is_meta(a): return bool(re.search(r'усі відповіді|всі відповіді|правильн', a))
def is_short(a): return len(a.split()) <= 4
meta = [e for e in entries if is_meta(e.get('answer',''))]
nonmeta = [e for e in entries if not is_meta(e.get('answer',''))]
short = [e for e in nonmeta if is_short(e.get('answer',''))]
other = [e for e in nonmeta if not is_short(e.get('answer',''))]

# Load bank to get refs
bank = json.load(open('banks/mzs-2026.fixed.json'))
qmap = {}
for sec in bank['sections']:
    for q in sec['questions']:
        qmap[q['id']] = q

def find_in_law(answer, ref):
    # get law file
    try:
        f = S.legislation_file(ref)
    except Exception as ex:
        return None, None, str(ex)
    if not f:
        return None, None, 'no file'
    try:
        html = open('laws/'+f, encoding='utf-8').read()
    except Exception as ex:
        return None, None, 'no read'
    arts = S.extract_articles(html)
    best = None
    for title, art in arts:
        m, ratio, words = S.answer_matches_article(answer, art)
        if m and (best is None or ratio > best[1]):
            best = (title, ratio)
    return best, f, None

print('=== OTHER (80): ref-error vs paraphrase ===')
ref_err = []
paraphrase = []
no_file = []
for e in other:
    q = qmap.get(e['qid'])
    ref = q['explain']['ref'] if q else e.get('ref','')
    answer = e['answer']
    best, f, err = find_in_law(answer, ref)
    if err:
        no_file.append((e['qid'], err))
        print('  NOFILE', e['qid'], err)
    elif best:
        ref_err.append((e['qid'], best[0], best[1]))
        print('  REFERR', e['qid'], '->', best[0], 'ratio', best[1])
    else:
        paraphrase.append(e['qid'])
        print('  PARAPH', e['qid'], '|', answer[:50])

print()
print('REF_ERROR candidates:', len(ref_err))
print('PARAPHRASE:', len(paraphrase))
print('NO_FILE:', len(no_file))
