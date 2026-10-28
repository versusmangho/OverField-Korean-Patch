# -*- coding: utf-8 -*-
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('translations.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

modified = [x for x in data if x.get('modified')]
print(f"Total modified entries in translations.json: {len(modified):,}")

by_table = {}
for x in modified:
    t = x.get('table_id')
    by_table[t] = by_table.get(t, 0) + 1

for t in sorted(by_table.keys()):
    print(f"  Table {t}: {by_table[t]:,} modified")

print("\n--- Recent Modified Samples (last 20) ---")
for item in modified[-20:]:
    print(f"[{item.get('uid')}] Table {item.get('table_id')} entry={item.get('entry_id')} field={item.get('field_idx')}")
    print(f"  JA: {item.get('ja')}")
    print(f"  KO: {item.get('ko')}")
