"""Ten-line review batches with a persisted five-clean-round stopping rule.

This only reads/writes review data. It never runs or patches the game.
"""
import json
import random
import secrets
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE / 'ten_by_five'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    RUN.mkdir(exist_ok=True)
    for path in (HERE.parent / 'translations.json', HERE / 'corrections.json'):
        backup = RUN / ('before_' + path.name)
        if not backup.exists():
            shutil.copy2(path, backup)
    ledger = read(RUN / 'status.json') if (RUN / 'status.json').exists() else {
        'batch_size': 10, 'required_clean_streak': 5, 'clean_streak': 0,
        'complete': False, 'rounds': [],
        'scope': 'Table 46 dialogue field 3, source length >= 15; not directly corrected or previously sampled',
    }
    if sys.argv[1] == 'finish':
        number = len(ledger['rounds']) + 1
        batch = read(RUN / f'round_{number:03}.json')
        submission = read(RUN / 'submit.json')
        verdicts = submission['verdicts']
        assert set(verdicts) == {s['uid'] for s in batch['samples']}
        assert all(v['status'] in {'pass', 'fail', 'deferred'} and v['reason'] for v in verdicts.values())
        corrections = read(HERE / 'corrections.json')
        rows = {x['uid']: x for x in read(HERE.parent / 'translations.json')}
        sources = read(HERE / 'random_review_sources.local.json')
        batch['changes'] = []
        for uid, text in submission.get('fixes', {}).items():
            row = rows[uid]
            assert row['table_id'] == 46 and row['field_idx'] == 3
            assert row['ja'] == sources[uid]
            batch['changes'].append({'uid': uid, 'source': sources[uid],
                                     'before': corrections.get(uid, row['ko']), 'after': text})
            corrections[uid] = text
        write(HERE / 'corrections.json', corrections)
        batch['verdicts'] = verdicts
        clean = all(v['status'] == 'pass' for v in verdicts.values())
        ledger['clean_streak'] = ledger['clean_streak'] + 1 if clean else 0
        ledger['rounds'].append({'round': number, 'seed': batch['seed'], 'clean': clean,
                                 'errors': sum(v['status'] != 'pass' for v in verdicts.values())})
        ledger['complete'] = ledger['clean_streak'] >= 5
        write(RUN / f'round_{number:03}.json', batch)
        write(RUN / 'status.json', ledger)
        print(json.dumps(ledger['rounds'][-1] | {'clean_streak': ledger['clean_streak'], 'complete': ledger['complete']}))
        return
    assert not ledger['complete']
    number = len(ledger['rounds']) + 1
    target = RUN / f'round_{number:03}.json'
    if target.exists():
        batch = read(target)
    else:
        rows = read(HERE.parent / 'translations.json')
        corrections = read(HERE / 'corrections.json')
        sources = read(HERE / 'random_review_sources.local.json')
        seen = set(corrections)
        seen.update(s['sample_uid'] for s in read(HERE / 'random_sample_2026-10-28.json')['samples'])
        for file in HERE.glob('random_review_round_*.json'):
            seen.update(s['uid'] for s in read(file)['samples'])
        for file in RUN.glob('round_*.json'):
            seen.update(s['uid'] for s in read(file)['samples'])
        pool = [x for x in rows if x['table_id'] == 46 and x['field_idx'] == 3 and x['uid'] not in seen
                and len(x['ja'].strip()) >= 15 and not x['is_key']]
        seed = secrets.randbits(64)
        selected = random.Random(seed).sample(pool, 10)
        batch = {'round': number, 'seed': seed, 'pool_size': len(pool), 'samples': []}
        dialogue = [x for x in rows if x['table_id'] == 46 and x['field_idx'] == 3]
        for x in selected:
            scene = x['key'].rsplit('_', 1)[0]
            near = [a for a in dialogue if a['key'].rsplit('_', 1)[0] == scene] if scene else dialogue
            i = near.index(x)
            batch['samples'].append({'uid': x['uid'], 'scene': scene, 'rows': [
                {k: a[k] for k in ('uid', 'key', 'speaker_ja')} |
                {'ko': corrections.get(a['uid'], a['ko']), 'source': sources[a['uid']]}
                for a in near[max(0, i - 1):i + 2]]})
        write(target, batch)
        write(RUN / 'status.json', ledger)
    for s in batch['samples']:
        print('\nSAMPLE', s['uid'])
        for x in s['rows']:
            print(x['uid'], x['key'], x['speaker_ja'], '|', x['source'], '|', x['ko'])


if __name__ == '__main__':
    main()
