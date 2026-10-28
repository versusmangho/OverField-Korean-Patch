# -*- coding: utf-8 -*-
import csv
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

os.makedirs('csv_spreadsheets', exist_ok=True)

with open('translations.json', 'r', encoding='utf-8') as f:
    translations = json.load(f)

target_tables = [
    (46, "Table_46_Story_Dialogues.csv"),
    (1,  "Table_01_Items_Encyclopedia.csv"),
    (7,  "Table_07_Skills_Buffs.csv"),
    (17, "Table_17_Equip_Passives.csv"),
    (20, "Table_20_Letters_Notices.csv"),
    (63, "Table_63_Minigames.csv")
]

all_combined_rows = []

for t_id, fname in target_tables:
    out_path = os.path.join('csv_spreadsheets', fname)
    t_items = [it for it in translations if it.get('table_id') == t_id and (it.get('ja', '').strip() or it.get('ko', '').strip())]
    
    with open(out_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["식별자", "화자", "원문", "현재 번역"])
        for it in t_items:
            uid = it.get('uid', '')
            key = it.get('key', '')
            identifier = f"{uid} ({key})" if key else uid
            
            spk_ko = it.get('speaker_ko', '').strip()
            spk_ja = it.get('speaker_ja', '').strip()
            if spk_ko and spk_ja and spk_ko != spk_ja:
                speaker = f"{spk_ko} ({spk_ja})"
            elif spk_ko:
                speaker = spk_ko
            elif spk_ja:
                speaker = spk_ja
            else:
                speaker = ""

            ja = it.get('ja', '')
            ko = it.get('ko', '')
            row = [identifier, speaker, ja, ko]
            writer.writerow(row)
            all_combined_rows.append([f"Table {t_id}", identifier, speaker, ja, ko])

    print(f"[+] {fname} 작성 완료: {len(t_items):,}개 행")

# 전체 통합 CSV도 작성
comb_path = os.path.join('csv_spreadsheets', 'Table_All_Combined.csv')
with open(comb_path, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(["테이블", "식별자", "화자", "원문", "현재 번역"])
    writer.writerows(all_combined_rows)

print(f"[+] Table_All_Combined.csv 작성 완료: {len(all_combined_rows):,}개 행")
