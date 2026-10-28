"""Draw five unreviewed Table 46 dialogue lines; never launches the game."""
import json
import random
import secrets
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    number = int(sys.argv[1])
    rows = json.loads((HERE.parent / 'translations.json').read_text(encoding='utf-8'))
    corrections = json.loads((HERE / 'corrections.json').read_text(encoding='utf-8'))
    sources = json.loads((HERE / 'random_review_sources.local.json').read_text(encoding='utf-8'))
    seen = set(corrections)
    first = json.loads((HERE / 'random_sample_2026-10-28.json').read_text(encoding='utf-8'))
    seen.update(s['sample_uid'] for s in first['samples'])
    for file in HERE.glob('random_review_round_*.json'):
        seen.update(s['uid'] for s in json.loads(file.read_text(encoding='utf-8'))['samples'])
    pool = [x for x in rows if x['table_id'] == 46 and x['field_idx'] == 3
            and x['uid'] not in seen and len(x['ja'].strip()) >= 15 and not x['is_key']]
    seed = secrets.randbits(32)
    samples = random.Random(seed).sample(pool, 5)
    out = {'round': number, 'seed': seed, 'pool_size': len(pool), 'samples': []}
    dialogues = [x for x in rows if x['table_id'] == 46 and x['field_idx'] == 3]
    for x in samples:
        scene = x['key'].rsplit('_', 1)[0]
        near = [a for a in dialogues if a['key'].rsplit('_', 1)[0] == scene]
        index = near.index(x)
        selected = near[max(0, index - 1):index + 2]
        out['samples'].append({'uid': x['uid'], 'scene': scene, 'rows': [
            {k: a[k] for k in ('uid', 'key', 'speaker_ja', 'ko')} |
            {'source': sources[a['uid']]} for a in selected]})
    target = HERE / f'random_review_round_{number:02}.json'
    if target.exists():
        raise FileExistsError(target)
    target.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
