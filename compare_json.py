# -*- coding: utf-8 -*-
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

f_game = r"translations.json"
f_repo = r"C:\Users\iw_mi\OneDrive\문서\OverField-Korean-Patch\translations.json"

print(f"Loading {f_game}...")
with open(f_game, "r", encoding="utf-8") as f:
    items_game = json.load(f)

print(f"Loading {f_repo}...")
with open(f_repo, "r", encoding="utf-8") as f:
    items_repo = json.load(f)

map_game = {x['uid']: x for x in items_game}
map_repo = {x['uid']: x for x in items_repo}

diff_ko = []
for uid, it_game in map_game.items():
    if uid in map_repo:
        it_repo = map_repo[uid]
        if it_game.get('ko') != it_repo.get('ko'):
            diff_ko.append((uid, it_game.get('ko'), it_repo.get('ko')))

print(f"Total differences in 'ko': {len(diff_ko):,}")
print("\n--- First 15 differences ---")
for uid, ko_game, ko_repo in diff_ko[:15]:
    print(f"[{uid}]")
    print(f"  GAME JSON: {ko_game}")
    print(f"  REPO JSON: {ko_repo}")
