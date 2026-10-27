"""검토한 번역만 JSON에 반영한다. 게임/번들/네트워크를 실행하지 않는다."""
import collections
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
TARGETS = {1, 7, 17, 20, 46, 63}

# 원문에 해당 인명이 존재할 때만 별칭을 정규화한다.
NAMES = {
    '詩': ('시', ['엘']), 'フェイ': ('페이', []),
    'イェンイェン': ('옌옌', ['영이', '예엔']),
    'ファンティーヌ': ('팡틴', ['판티누', '판티느']),
    '咲': ('사키', []), 'ナオキ': ('나오키', []),
    'コク': ('코크', ['고쿠', '코쿠']), 'コクマ': ('코쿠마', []),
    '小伏': ('코부시', ['코후시']), 'トト': ('토토', []),
    'ミリア': ('밀리아', []), 'ガゼット': ('가제터', ['가제트']),
    'ハーミット': ('헤르메트', ['허미트']), 'リン': ('린', []),
    'ロロメ': ('로로메', []), 'レクシー': ('렉시', ['렉']),
    'ダヴ': ('도브', ['더브', '다브']), 'ミャオ': ('미오', ['미아오']),
    'ココ': ('코코', ['카코']), 'フレイ': ('프레이', ['플레이버', '플레']),
    'モモ': ('모모', ['모모코', '복숭아']), 'レモン': ('레몬', ['닝멍', '닝']),
    'ヒカリ': ('히카리', []), 'レイシー': ('레이시', []),
    'ムンシャ': ('문샤인', ['문']), 'リコ': ('리코', ['인']),
    'オーレラ': ('오렐리아', ['오르', '오레라']),
    'ナイシー': ('나이시', []),
    'ミカン・シトラス': ('미칸 시트러스', ['정청청']),
    'ミカン': ('미칸', ['정청청', '청청']),
    'アズサ': ('아즈사', []), 'アヤ': ('아야', []), '部長': ('부장', []),
    'チャン': ('상태석', ['상']), 'シェリー': ('셜리', ['세일리']),
    'メアリー': ('메리', []), 'シュウ・シツエン': ('주치원', []),
    '黒川': ('쿠로카와', []), '黒川京亮': ('쿠로카와 쿄스케', []),
    'スースー': ('소소', []), 'ウナ': ('운나', []), 'アイナ': ('아이나', []),
    '蝶子': ('나비', []), 'C.A': ('C.A', []), 'パンオン': ('판', []),
    '博士': ('박사', []), 'リーダー': ('리더', []),
    '“魔女”': ('“마녀”', []), '魔女？': ('마녀?', []), '魔女': ('마녀', []),
    'ドーラ': ('도라', []), 'ドーラ？': ('도라?', []),
    '研究員': ('연구원', []), '研究員？': ('연구원?', []),
    'スタッフ': ('스태프', []), '見知らぬ男': ('낯선 남자', []),
    '通行人': ('행인', []), '座長': ('좌장', []), '子猫': ('새끼 고양이', []),
    '皆': ('일동', []), '六人': ('여섯 명', []), '？': ('?', []), '？？': ('??', []),
    '謎の少女': ('신비한 소녀', []), '「ヒカリ」': ('「히카리」', []),
}
NAMES.update({
    'ロロメ': ('로로메', ['로로메이']),
    'アレタ': ('알레타', ['레이']), '丹': ('단', []), 'ダンニア': ('단', []),
    '四喜': ('사희', ['희']), 'キキ': ('키키', ['치치', '치']),
    'ウィル': ('윌', ['벨베르']), 'カトリーナ': ('카트리나', ['카']),
    'パルジファル': ('파르치팔', []), 'リョウハク': ('료하쿠', []),
    'モーリ': ('몰리', []), 'セージ': ('세이지', []), 'パン': ('판', []),
})

# 스킬명과 해당 스킬을 참조하는 설명을 함께 맞춘다.
SKILLS = {
    'ジャンボカッター': ('점보 커터', ['회전 돌진', '회선 돌진']),
    '砕けた嘘': ('거짓 파쇄', ['깨진 거짓']),
    'エンドスラッシュ': ('마무리 베기', ['종결베기']),
    '取り繕う嘘': ('거짓말을 감추는 방법', ['거짓말을 덮는 길']),
    '身柄確保': ('체포의 순간', ['신병 확보']),
    'ルートマーカー': ('경로 표식', ['여기로 정했다!', '랜드마크 포토존', '랜드마크 포도존', '체크포인트']),
    '緊急インタビュー': ('긴급 취재', ['긴급 인터뷰']),
    'ブラインド撮影': ('잠입 조사', ['비밀 취재']),
    '裁きの銃陣': ('단죄의 사격진', ['심판의 창진', '심판의 총진']),
    'ほうきの星屑': ('빗자루 별가루', ['빗자루 연기 속박']),
    'メテオイックスパイラル': ('유성 회전', ['메테오 스핀']),
    'ジャスティススパーク！': ('저스티스 스파크!', []),
    'マジックバレット': ('마법 탄환', []),
    '縫い針ダッシュ': ('재봉사 돌진', []), 'ハサミ突撃': ('가위 급습', []),
    'アイドルリズム': ('아이돌 리듬', ['콘서트']),
    'ローズサイン': ('장미 각인', []), 'フラワーダンス': ('꽃잎 걸음', ['블라썸 스텝']),
    '引導': ('관문', ['릴레이']), 'あかつき': ('여명', ['새벽']),
    '衝天拳': ('승룡권', ['충천권']),
    '時の飛針': ('시간의 단도', []), '回転時針': ('시곗바늘 부메랑', []),
    'みんなに飴をあげる！': ('모두에게 사탕을 줄게!', []),
    '飴をあげる！': ('사탕을 줄게!', []),
    '熱湯おかわり': ('뜨거운 차 한 잔 더', []), '大合唱': ('대합창', []),
    '大儲け': ('대박', []), '落書き紙棒': ('낙서 종이봉', []),
    '棺に潜む影': ('관에 숨은 그림자', ['관중박영']),
    'デスの契約': ('죽음의 계약', ['사신계약']),
    'ヴァンパイアスウープ': ('뱀파이어 급습', ['혈영천강']),
    'アニメの主人公': ('애니메이션의 주인공', []),
}

TERMS = {
    'ロータラボラトリー': ('로타 연구소', ['로타 익스플로어 퓨처테크', '로타라 보라토리', '로타 라보라토리', '로타 테크']),
    '星物質': ('별 물질', ['오각별 마테리아', '스타 매터']),
    'プネウマイズム': ('프네우마이즘', ['회령학', '혼령주의']),
    'プネウマ会': ('프네우마회', ['혼령회', '회령학회', '푸네우마회']),
    'プネウマ歴史研究会': ('프네우마 역사연구회', ['혼령회 역사연구소', '푸네우마 역사 연구회']),
    'シュタイン結晶': ('슈타인 결정', ['스테인 결정']),
    'シュタイン素': ('슈타인소', ['스테인 원소', '슈타인 원소']),
    '探索部': ('탐색부', ['탐색팀']), '研究部': ('연구부', ['연구팀']),
    '技術部': ('기술부', ['기술팀']), '人事部': ('인사부', ['인사팀']),
    '資源部': ('자원부', ['자원팀']),
}


def replace_name(text, alias, canonical):
    # 독립 인명 또는 조사·존칭이 뒤따르는 경우만 치환. 다른 낱말 내부는 제외.
    pattern = re.compile(r'(?<![가-힣A-Za-z])' + re.escape(alias)
                         + r'(?:(은|는|이|가|을|를|과|와|으로|로|의|에게|한테|처럼|부터|까지|도|만|랑)(?![가-힣])|(?=$|[^가-힣A-Za-z]|씨|님|선배|언니|쨩|짱))')
    final = ord(canonical[-1])
    jong = (final - 0xAC00) % 28 if 0xAC00 <= final <= 0xD7A3 else 0
    def repl(m):
        particle = m.group(1)
        pairs = [('은', '는'), ('이', '가'), ('을', '를'), ('과', '와')]
        for yes, no in pairs:
            if particle in (yes, no):
                return canonical + (yes if jong else no)
        if particle in ('으로', '로'):
            return canonical + ('으로' if jong and jong != 8 else '로')
        return canonical + (particle or '')
    return pattern.sub(repl, text)


def source_tokens(text):
    return collections.Counter(re.findall(r'\{[^{}]*\}|\$[^$\n]+\$|</?[A-Za-z][^>]*>', text))


def main():
    source = ROOT / 'translations.json'
    backup = HERE / 'translations.before-review.json'
    if not backup.exists():
        shutil.copy2(source, backup)
    items = json.loads(backup.read_text(encoding='utf-8'))
    by_uid = {x['uid']: x for x in items}
    overrides = json.loads((HERE / 'corrections.json').read_text(encoding='utf-8'))
    source_overrides = json.loads((HERE / 'source_overrides.json').read_text(encoding='utf-8'))
    overrides_by_source = {(by_uid[uid]['table_id'], by_uid[uid]['ja']): text
                           for uid, text in overrides.items()
                           if by_uid[uid]['table_id'] in {1, 7, 17, 63} and by_uid[uid]['ja']}
    families = json.loads((HERE / 'numeric_families.json').read_text(encoding='utf-8'))
    patterns = []
    for uid, template in families.items():
        original = by_uid[uid]['ja']
        # Full-string matching prevents partial rewrites of different effects.
        chunks = re.split(r'(\d+(?:\.\d+)?)', original)
        pattern = ''.join(r'(\d+(?:\.\d+)?)' if i % 2 else re.escape(part)
                          for i, part in enumerate(chunks))
        patterns.append((by_uid[uid]['table_id'], re.compile(pattern), template, uid))
    changes, token_errors = [], []
    for x in items:
        if x['table_id'] not in TARGETS or x.get('is_key'):
            continue
        before, before_speaker = x['ko'], x.get('speaker_ko', '')
        reasons = []
        if x['uid'] in overrides:
            x['ko'] = overrides[x['uid']]
            reasons.append('직접 원문 대조·윤문')
        elif (x['table_id'], x['ja']) in overrides_by_source:
            x['ko'] = overrides_by_source[x['table_id'], x['ja']]
            reasons.append('동일 원문 검토문 반영')
        else:
            for tid, pattern, template, uid in patterns:
                match = pattern.fullmatch(x['ja']) if tid == x['table_id'] else None
                if match:
                    values = {f'n{i}': value for i, value in enumerate(match.groups())}
                    x['ko'] = template.format(**values)
                    reasons.append('정형 설명 원문 대조:' + uid)
                    break
        # Longer source names take precedence over short forms.
        ja, ko = x.get('ja', ''), x['ko']
        applied_aliases = set()
        for japanese, (canonical, aliases) in sorted(NAMES.items(), key=lambda v: len(v[0]), reverse=True):
            # ココナッツ(코코넛), モモウーロン(복숭아 우롱) 등의 부분 일치 제외.
            if not re.search(re.escape(japanese) + r'(?![ァ-ヺー一-鿿])', ja):
                continue
            for alias in aliases:
                if alias in applied_aliases:
                    continue
                replaced = replace_name(ko, alias, canonical)
                if replaced != ko:
                    applied_aliases.add(alias)
                    reasons.append('원문 인명 대조')
                    ko = replaced
        # Unambiguous system terminology, bounded to the relevant source term.
        for jp, aliases, canonical in [
            ('会心率', ['치명타율', '치명률'], '치명타 확률'),
            ('射撃', ['슈팅'], '사격'),
            ('AP', ['행동 포인트', '행동력'], 'AP'),
            ('クールダウン', ['쿨타임'], '재사용 대기시간'),
            ('ロータフェス', ['로터 페스티벌', '로터페스', '로터 페스', '로타페스'], '로타 페스티벌'),
            ('探索部', ['탐험부', '탐사부'], '탐색부'),
            ('イン元素', ['인 원소'], '인륨'),
        ]:
            if jp in ja:
                for alias in aliases:
                    if alias in ko:
                        ko = ko.replace(alias, canonical)
                        reasons.append('원문 용어 대조')
        if '力場' in ja and x['table_id'] in {1, 7, 17}:
            normalized = re.sub(r'마법(?: 속성| 계열)?(?= 피해)', '역장', ko)
            normalized = re.sub(r'마법(?= 계열)', '역장', normalized)
            if normalized != ko:
                reasons.append('원문 용어 대조')
            ko = normalized
        if 'インリウム' in ja:
            ko = ko.replace('에테리움 원소', '인륨').replace('인리움', '인륨')
        if x['table_id'] == 17:
            for old, new in [('프론티어 아카이브', '프론티어 자료'), ('프론티어 기록', '프론티어 자료'),
                             ('영상 슬롯', '포토 슬롯'), ('프래그먼트 슬롯', '포토 슬롯'),
                             ('스페셜 해금', '특성 해금'), ('Break', '브레이크')]:
                if old in ko:
                    reasons.append('원문 용어 대조')
                    ko = ko.replace(old, new)
        x['ko'] = ko
        if x['table_id'] == 7 and x['field_idx'] >= 4:
            # 스킬 수치 라벨: 전각 콜론·잘못된 인덱스/서식을 원문의 C# 치환자로 복원.
            token_pattern = r'\{[^{}]*\}'
            source_sequence = re.findall(token_pattern, ja)
            target_sequence = re.findall(token_pattern, x['ko'])
            if source_sequence and len(source_sequence) == len(target_sequence) and source_sequence != target_sequence:
                iterator = iter(source_sequence)
                x['ko'] = re.sub(token_pattern, lambda _: next(iterator), x['ko'])
                reasons.append('치환자 인덱스·서식 원문 복원')
        for japanese, (canonical, aliases) in TERMS.items():
            if japanese in ja:
                for alias in aliases:
                    if alias in x['ko']:
                        x['ko'] = x['ko'].replace(alias, canonical)
                        reasons.append('고유명사·기관명 통일')
        if x['table_id'] in {1, 7, 17} and 'AP' in ja:
            x['ko'] = re.sub(r'AP(?:이|가)(?![가-힣])', 'AP가', x['ko'])
            x['ko'] = re.sub(r'AP(?:을|를)(?![가-힣])', 'AP를', x['ko'])
            x['ko'] = re.sub(r'AP(?:은|는)(?![가-힣])', 'AP는', x['ko'])
        ko = x['ko']
        for japanese, (canonical, aliases) in SKILLS.items():
            if japanese in ja and x['table_id'] in {1, 7, 17}:
                if ja == japanese:
                    x['ko'] = canonical
                else:
                    for alias in aliases:
                        x['ko'] = x['ko'].replace(alias, canonical)
                if x['ko'] != ko:
                    reasons.append('스킬명 통일')
                ko = x['ko']
        if x['table_id'] in {1, 7, 17} and ja in NAMES:
            x['ko'] = NAMES[ja][0]
            reasons.append('독립 인명 필드 통일')
        # field_idx 2 is the speaker display name only in Table 46.
        if x['table_id'] == 46:
            japanese_speaker = x.get('speaker_ja', '')
            if japanese_speaker in NAMES:
                canonical = NAMES[japanese_speaker][0]
                x['speaker_ko'] = canonical
                if x['field_idx'] == 2 and x['ja'] == japanese_speaker:
                    x['ko'] = canonical
                if x['speaker_ko'] != before_speaker or x['ko'] != ko:
                    reasons.append('화자 표시 통일')
        ja_before = x['ja']
        if x['uid'] in source_overrides:
            x['ja'] = source_overrides[x['uid']]
            reasons.append('실제 번들 원문 재동기화')
        if before != x['ko'] or before_speaker != x.get('speaker_ko', '') or ja_before != x['ja']:
            # Preserve original_ko so the existing packer can continue tracking edits.
            if before != x['ko']:
                x['modified'] = True
            record = dict(uid=x['uid'], table_id=x['table_id'], speaker=x.get('speaker_ko'),
                          ja=x['ja'], ja_before=ja_before, before=before, after=x['ko'],
                          speaker_before=before_speaker, reasons=sorted(set(reasons)))
            changes.append(record)
            if source_tokens(before) != source_tokens(x['ko']):
                # Fixing pre-existing missing tokens is allowed only if matching the source exactly.
                if source_tokens(x['ja']) != source_tokens(x['ko']):
                    token_errors.append(x['uid'])
    if token_errors:
        raise ValueError('치환자/태그 확인 필요: ' + ', '.join(token_errors))
    # Only JSON data changes; this utility never imports any patching module.
    temporary = source.with_suffix('.review.tmp')
    temporary.write_text(json.dumps(items, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(source)
    (HERE / 'changes.json').write_text(json.dumps(changes, ensure_ascii=False, indent=2), encoding='utf-8')
    groups = collections.defaultdict(list)
    for x in items:
        if x['table_id'] == 46 and x.get('field_idx') == 3:
            groups[x.get('speaker_ja', '')].append(x)
    evidence = ['# 화자별 원문 증거', '', '성격·관계는 아래 대사와 번역 기준에 근거한다. 빈 화자를 억지로 기명 인물에 합치지 않는다.', '']
    for name, rows in groups.items():
        evidence += [f'## {name or "화자 메타데이터 없음"}', '', f'수록 대사 필드: {len(rows)}개.', '']
        for x in rows[:4]:
            evidence += [f'- `{x["uid"]}`: {x["ja"]}', f'  - 한국어: {x["ko"]}']
        evidence.append('')
    (HERE / 'speaker_evidence.md').write_text('\n'.join(evidence), encoding='utf-8')
    print(json.dumps(collections.Counter(x['table_id'] for x in changes), ensure_ascii=False))


if __name__ == '__main__':
    main()
