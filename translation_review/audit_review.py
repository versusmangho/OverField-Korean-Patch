"""번역 파일과 패치 산출물의 정적 데이터 대조. 게임을 실행하지 않는다."""
import ast
import collections
import hashlib
import json
import re
import sys
import zlib
from pathlib import Path

from apply_review import TARGETS
from build_reviewed_payload import UnityPy, textasset, key_fields

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    before = json.loads((HERE / 'translations.before-review.json').read_text(encoding='utf-8'))
    after = json.loads((ROOT / 'translations.json').read_text(encoding='utf-8'))
    changes = json.loads((HERE / 'changes.json').read_text(encoding='utf-8'))
    assert len(before) == len(after)
    assert [x['uid'] for x in before] == [x['uid'] for x in after]
    assert collections.Counter(x['uid'] for x in before) == collections.Counter(x['uid'] for x in after)
    # 기존 빈 개발용 슬롯에는 중복 UID가 있다. 보존하되 수정 대상으로 삼지 않는다.
    duplicate_uids = {uid for uid, count in collections.Counter(x['uid'] for x in after).items() if count > 1}
    assert not duplicate_uids.intersection(c['uid'] for c in changes)
    allowed = {'ko', 'modified', 'speaker_ko', 'ja'}
    for old, new in zip(before, after):
        if old['table_id'] not in TARGETS or old.get('is_key'):
            assert old == new, old['uid']
        assert all(old.get(k) == new.get(k) for k in set(old) | set(new) if k not in allowed), old['uid']
        if old['ko'] != new['ko']:
            assert new['modified'] is True
    for name in ['apply_review.py', 'build_reviewed_payload.py', 'audit_review.py']:
        ast.parse((HERE / name).read_text(encoding='utf-8'), filename=name)

    def assets(data):
        env = UnityPy.load(data)
        return {obj.path_id: (textasset(obj.get_raw_data())[0], obj.get_raw_data())
                for obj in env.objects if obj.type.name == 'TextAsset'}
    original_assets = assets(zlib.decompress((HERE / 'patch_payload.before-review.dat').read_bytes()))
    packaged_assets = assets((HERE / 'reviewed.bundle').read_bytes())
    assert original_assets.keys() == packaged_assets.keys()
    for key, (name, raw) in original_assets.items():
        if name != 'String_Korea':
            assert packaged_assets[key] == (name, raw), name
    old_script = next(textasset(raw)[1] for name, raw in original_assets.values() if name == 'String_Korea')
    new_script = next(textasset(raw)[1] for name, raw in packaged_assets.values() if name == 'String_Korea')
    old_fields, new_fields = key_fields(old_script), key_fields(new_script)
    assert old_fields.keys() == new_fields.keys()
    by_uid = {x['uid']: x for x in after}
    expected = {(by_uid[c['uid']]['table_id'], by_uid[c['uid']]['entry_id'], by_uid[c['uid']]['field_idx']): c['after'].encode('utf-8')
                for c in changes if c['before'] != c['after']}
    for key, value in old_fields.items():
        assert new_fields[key] == expected.get(key, value), key

    candidates = []
    reviewed = {c['uid'] for c in changes if any(r.startswith(('직접', '동일', '정형')) for r in c['reasons'])}
    for x in after:
        if x['table_id'] not in TARGETS or x.get('is_key'):
            continue
        ja, ko = x['ja'], x['ko']
        reasons = []
        if re.search(r'技能描述|スキル説明[-\d]|パッシブ説明|テストスキル|新サルベージャー|新キャラクター', ja):
            reasons.append('원문 자체가 임시 설명·미확정 명칭')
        if ja.strip() and not ko.strip():
            reasons.append('빈 번역')
        if re.search('[ぁ-ヿ]', ko):
            reasons.append('한국어 안 일본어 문자 잔류 후보')
        if re.search(r'#REF!|#VALUE!|#N/A', ko):
            reasons.append('스프레드시트 오류 문자열')
        if len(ja) >= 40 and len(ko) < len(ja) * .28:
            reasons.append('지나치게 짧은 번역: 누락 여부 검토')
        def placeholders(s):
            return collections.Counter(re.findall(r'\{\d[^{}]*\}|\{\|\}|\$[^$\n]+\$', s))
        if placeholders(ja) != placeholders(ko):
            reasons.append('원문과 치환자 차이: 실제 형식 확인 필요')
        if x['uid'] not in reviewed and x['table_id'] in {7, 17} and x['field_idx'] == 2:
            def numbers(s):
                s = re.sub(r'\{[^{}]*\}|\$[^$\n]+\$|<[^>]*>', '', s)
                return collections.Counter(re.findall(r'\d+(?:\.\d+)?', s))
            if numbers(ja) != numbers(ko):
                reasons.append('숫자 표기 차이 후보: 한글 수사·세트 표기 등 오탐 가능')
        if reasons:
            candidates.append({k: x.get(k) for k in ['uid', 'table_id', 'speaker_ko', 'ja', 'ko']} | {'reasons': reasons})
    (HERE / 'needs_review.json').write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding='utf-8')
    counts = []
    for table in sorted(TARGETS):
        rows = [c for c in changes if c['table_id'] == table]
        counts.append((table, sum(c['before'] != c['after'] for c in rows),
                       sum(c['before'] == c['after'] and c['speaker_before'] != c['speaker'] for c in rows),
                       sum(c['uid'] in reviewed and c['before'] != c['after'] for c in rows)))
    lines = ['# 번역 교정 결과', '', '작업일: 2026-10-28', '',
             '전체 문장 전수 윤문 완료를 의미하지 않는다. 직접 원문 대조, 동일 원문·수치별 변형의 검토문 적용, 인명·용어 통일을 함께 진행했다. 인명·용어만 바뀐 문장은 전체 문장 검토 완료로 세지 않는다.', '',
             '| Table | 번역 본문 변경 | 화자 메타데이터만 변경 | 원문 대조·정형 설명 교정으로 본문 변경 |',
             '|---|---:|---:|---:|']
    lines += [f'| {t} | {text} | {meta} | {direct} |' for t, text, meta, direct in counts]
    lines += ['', f'본문 변경 합계: {sum(r[1] for r in counts):,}개. 원문 번들과 대조해 패킹한 필드: {len(expected):,}개.', '',
              '## 주요 수정', '',
              '- 캐릭터 이름, 별칭, 화자 표시, 스킬 제목과 본문 참조를 통일했다.',
              '- 대사가 첫 구절 뒤에 잘린 행을 원문에 따라 복원하고 화자별 말투를 적용했다.',
              '- AP 고정값/비율, 시전자/대상, 장착자/팀 전체, 미만/이하, 회복량 기준, 피해 종류와 누락된 효과를 교정했다.',
              '- Table 20의 편지·학술지·공지에 원문에 없는 단정·정보를 덜어내고 누락된 날짜·문장을 복원했다.',
              '- Table 63은 21개 비어 있지 않은 필드를 모두 대조했고, 수정이 필요한 규칙·문구 8개를 고쳤다.', '',
              '## 원문 출처의 차이', '',
              'JSON의 ja 필드 일부는 실제 번들의 String_Japanese와 달랐다. source_overrides.json의 원문을 우선해 다시 동기화했다. 특히 17_32040 계열은 실제 원문이 브레이크 발동이며, 17_40160000 계열은 회피다. 7_30105000 계열은 실제 번들의 전체 스티치/실 거두기 설명을 복원했다. 기존의 짧은 JSON만 믿고 작성했던 교정안은 폐기했다.',
              '46_1289937896_3은 대응 일본어가 번들에 없어, 기존 한국어 필드의 정확한 일치로 위치를 확인하고 JSON 원문을 사용했다. 공식 설정이 검증되었다는 뜻은 아니다.', '',
              '## 데이터 대조 결과', '',
              f'- 전체 JSON {len(after):,}개 행의 UID·순서·구조 유지. 대상 밖 테이블·키·original_ko 유지.',
              '- 변경된 필드의 치환자와 태그를 대조했다. 기존의 잘못된 태그는 원문 형식에 맞춰 복원했다.',
              '- 생성한 번들을 다시 읽어 변경 대상 값 및 나머지 String_Korea 텍스트 필드 유지 여부를 대조했다.',
              f'- String_Korea 외 TextAsset {len(original_assets)-1}개 원시 데이터가 기존 페이로드와 동일하다. Voice_Korea도 보존했다.',
              '- 게임·런처·GUI 패처를 실행하지 않았다. 인게임 표시·줄바꿈·실제 효과 동작 검증은 생략했다.', '',
              '## 추가 검토 후보', '', f'needs_review.json에 {len(candidates):,}개 후보를 기록했다. 숫자를 한글로 쓴 경우·빈 개발용 슬롯 등 오탐을 포함하므로 확정 오류 수가 아니다.',
              '원문부터 技能描述20％ 등의 임시 설명인 항목, 신규 캐릭터 코드, 혼합 언어와 비정상적으로 큰 수치는 근거 없이 능력이나 이름을 만들어 채우지 않는다. 일반 문체의 자연스러움은 자동 검사로 완전하게 판정할 수 없다.', '',
              '## 적용과 백업', '',
              '- translations.before-review.json: 작업 전 원본. original_ko와 별도로 이번 작업 직전 상태를 보관한다.',
              '- changes.json: UID별 수정 전후, 화자, 교정 사유 및 원문 출처 변경.',
              '- reviewed_payload.dat / reviewed.bundle / reviewed__info: 교정본 패치 데이터.',
              '- patch_payload.before-review.dat: 기존 런처 페이로드.',
              '- 기존 CSV/XLSX는 자동 덮어쓰기하지 않았다. 예전 시트를 다시 가져오면 교정본이 되돌아갈 수 있으므로 주의한다.', '']
    (HERE / 'review_report.md').write_text('\n'.join(lines), encoding='utf-8')
    summary = {'counts': counts, 'text_fields': len(expected), 'candidate_count': len(candidates),
               'candidate_reasons': collections.Counter(reason for x in candidates for reason in x['reasons']),
               'json_sha256': hashlib.sha256((ROOT / 'translations.json').read_bytes()).hexdigest()}
    (HERE / 'audit_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
