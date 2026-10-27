"""기존 페이로드의 검토된 String_Korea 필드만 손실 없이 교체한다.

게임과 GUI 패처를 실행하지 않으며, 결과물은 이 디렉터리에만 생성한다.
"""
import collections
import json
import re
import struct
import zlib
import sys
from pathlib import Path

import UnityPy

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def varint(data, offset):
    value = shift = 0
    for _ in range(10):
        if offset >= len(data):
            raise ValueError('잘린 varint')
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        if not byte & 128:
            return value, offset
        shift += 7
    raise ValueError('varint 범위 초과')


def encode(value):
    out = bytearray()
    while value > 127:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def fields(data):
    offset = 0
    while offset < len(data):
        start = offset
        tag, offset = varint(data, offset)
        wire = tag & 7
        if wire == 0:
            value, offset = varint(data, offset)
        elif wire == 2:
            length, offset = varint(data, offset)
            end = offset + length
            if end > len(data):
                raise ValueError('잘린 length-delimited 필드')
            value = data[offset:end]
            offset = end
        elif wire in (1, 5):
            end = offset + (8 if wire == 1 else 4)
            if end > len(data):
                raise ValueError('잘린 고정 길이 필드')
            value, offset = data[offset:end], end
        else:
            raise ValueError(f'지원하지 않는 wire type: {wire}')
        yield tag, value, data[start:offset]


def wrap(tag, data):
    return encode(tag) + encode(len(data)) + data


def textasset(raw):
    length = struct.unpack_from('<i', raw)[0]
    name = raw[4:4 + length].decode('utf-8')
    offset = (4 + length + 3) & ~3
    size = struct.unpack_from('<i', raw, offset)[0]
    return name, raw[offset + 4:offset + 4 + size], raw[:offset]


def key_fields(script):
    result = {}
    for table_tag, table, _ in fields(script):
        if table_tag & 7 != 2:
            continue
        for entry_tag, entry, _ in fields(table):
            if entry_tag & 7 != 2:
                continue
            entry_fields = list(fields(entry))
            entry_id = next((v for t, v, _ in entry_fields if t == 8), None)
            for index, (tag, value, _) in enumerate(entry_fields):
                if tag & 7 == 2:
                    result[(table_tag >> 3, entry_id, index)] = value
    return result


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    payload = ROOT / 'patch_payload.dat'
    baseline_payload = HERE / 'patch_payload.before-review.dat'
    if not baseline_payload.exists():
        baseline_payload.write_bytes(payload.read_bytes())
    env = UnityPy.load(zlib.decompress(baseline_payload.read_bytes()))
    assets = {}
    for obj in env.objects:
        if obj.type.name == 'TextAsset':
            name, script, prefix = textasset(obj.get_raw_data())
            assets[name] = (obj, script, prefix)
    original_fields = key_fields(assets['String_Japanese'][1])
    korean_fields = key_fields(assets['String_Korea'][1])
    items = {x['uid']: x for x in json.loads((ROOT / 'translations.json').read_text(encoding='utf-8'))}
    changes = json.loads((HERE / 'changes.json').read_text(encoding='utf-8'))
    updates = {}
    fallback_source = []
    for change in changes:
        if change['before'] == change['after']:
            continue
        x = items[change['uid']]
        key = (x['table_id'], x['entry_id'], x['field_idx'])
        if original_fields.get(key, b'').decode('utf-8') != x['ja']:
            if (not original_fields.get(key)
                    and korean_fields.get(key, b'').decode('utf-8') == change['before']):
                fallback_source.append(x['uid'])
            else:
                raise ValueError(f'일본어 원문/필드 위치 불일치: {x["uid"]}')
        updates[key] = x['ko'].encode('utf-8')
    applied = collections.Counter()
    obj, script, prefix = assets['String_Korea']
    rebuilt = bytearray()
    for table_tag, table, table_raw in fields(script):
        if table_tag & 7 != 2 or table_tag >> 3 not in {1, 7, 17, 20, 46, 63}:
            rebuilt += table_raw
            continue
        new_table = bytearray()
        for entry_tag, entry, entry_raw in fields(table):
            if entry_tag & 7 != 2:
                new_table += entry_raw
                continue
            entry_fields = list(fields(entry))
            entry_id = next((v for t, v, _ in entry_fields if t == 8), None)
            new_entry = bytearray()
            for index, (tag, value, raw) in enumerate(entry_fields):
                key = (table_tag >> 3, entry_id, index)
                if key in updates:
                    if tag & 7 != 2:
                        raise ValueError(f'텍스트가 아닌 필드: {key}')
                    new_entry += wrap(tag, updates[key])
                    applied[key] += 1
                else:
                    new_entry += raw
            new_table += wrap(entry_tag, new_entry)
        rebuilt += wrap(table_tag, new_table)
    invalid = [key for key in updates if applied[key] != 1]
    if invalid:
        raise ValueError(f'패킹 대상 누락 또는 중복: {invalid[:10]}')
    raw = prefix + struct.pack('<i', len(rebuilt)) + rebuilt
    raw += b'\0' * (-len(raw) % 4)
    obj.set_raw_data(bytes(raw))
    obj.byte_size = len(raw)
    bundle = env.file.save(packer='lz4')
    (HERE / 'reviewed.bundle').write_bytes(bundle)
    (HERE / 'reviewed_payload.dat').write_bytes(zlib.compress(bundle, 9))
    crc = f'{zlib.crc32(bundle) & 0xffffffff:08x}'.encode('ascii')
    (HERE / 'reviewed__info').write_bytes(struct.pack('<H', 8) + crc + struct.pack('<q', len(bundle)))
    (HERE / 'payload_report.json').write_text(json.dumps({
        'changed_text_fields': len(updates), 'applied_once': len(applied),
        'bundle_size': len(bundle), 'crc32': crc.decode(),
        'base_payload': baseline_payload.name,
        'modified_asset': 'String_Korea', 'all_other_assets': 'preserved',
        'missing_japanese_verified_by_exact_korean': fallback_source,
        'game_executed': False, 'installed_game_files_written': False,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'패킹 완료: {len(updates)}개 필드, {len(bundle)} bytes')


if __name__ == '__main__':
    main()
