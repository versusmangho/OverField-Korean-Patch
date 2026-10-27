"""
OverField YooAsset 한국어/일본어 텍스트 패치 코어 라이브러리
"""

import os
import sys
import json
import struct
import shutil
import zipfile
import UnityPy

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STREAMING_BUNDLE = os.path.join(BASE_DIR, "launcher_Data", "StreamingAssets", "yoo", "DefaultPackage", "d36af905d36461838e80ed5db5090c65.bundle")
CACHE_DIR = os.path.join(BASE_DIR, "launcher_Data", "yoo", "DefaultPackage", "CacheFiles", "68", "68a9e72732e99edf100d6e4a6f692583")
CACHE_DATA = os.path.join(CACHE_DIR, "__data")
WORK_JSON = os.path.join(BASE_DIR, "translations.json")

def parse_varint(buf, offset):
    res = 0; shift = 0
    while True:
        b = buf[offset]; offset += 1; res |= (b & 0x7f) << shift; shift += 7
        if not (b & 0x80): break
    return res, offset

def encode_varint(val):
    res = bytearray()
    while True:
        b = val & 0x7f; val >>= 7
        if val: res.append(b | 0x80)
        else: res.append(b); break
    return bytes(res)

def extract_script(raw):
    name_len = struct.unpack_from('<i', raw, 0)[0]
    name_end = 4 + name_len
    if name_end % 4 != 0: name_end += 4 - (name_end % 4)
    script_len = struct.unpack_from('<i', raw, name_end)[0]
    return raw[name_end+4:name_end+4+script_len]

def make_textasset_raw(name_str, script_bytes):
    name_bytes = name_str.encode('utf-8')
    name_len = len(name_bytes)
    name_pad = (4 - (name_len % 4)) % 4
    
    script_len = len(script_bytes)
    data = bytearray()
    data += struct.pack('<i', name_len) + name_bytes + (b'\x00' * name_pad)
    data += struct.pack('<i', script_len) + script_bytes
    
    end_pad = (4 - (len(data) % 4)) % 4
    data += b'\x00' * end_pad
    return bytes(data)

def parse_protobuf_tables(raw_bytes):
    tables = {}
    offset = 0
    while offset < len(raw_bytes):
        tag, offset = parse_varint(raw_bytes, offset)
        fn = tag >> 3
        l, offset = parse_varint(raw_bytes, offset)
        t_buf = raw_bytes[offset:offset+l]
        offset += l
        
        entries = []
        sub_off = 0
        while sub_off < len(t_buf):
            _, sub_off = parse_varint(t_buf, sub_off)
            el, sub_off = parse_varint(t_buf, sub_off)
            entry_buf = t_buf[sub_off:sub_off+el]
            sub_off += el
            
            item_off = 0
            fields = []
            item_id = 0
            while item_off < len(entry_buf):
                itag, item_off = parse_varint(entry_buf, item_off)
                iw = itag & 7
                ifn = itag >> 3
                if iw == 0:
                    v, item_off = parse_varint(entry_buf, item_off)
                    if ifn == 1: item_id = v
                    fields.append({'tag': itag, 'wire': iw, 'fn': ifn, 'val': v})
                elif iw == 2:
                    sl, item_off = parse_varint(entry_buf, item_off)
                    s_raw = entry_buf[item_off:item_off+sl]
                    item_off += sl
                    fields.append({'tag': itag, 'wire': iw, 'fn': ifn, 'val': s_raw.decode('utf-8', errors='ignore')})
                else:
                    break
            entries.append({'id': item_id, 'fields': fields})
        tables[fn] = entries
    return tables

def save_translations_to_json(items, json_path=WORK_JSON):
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

def load_translations_from_json(json_path=WORK_JSON):
    if not os.path.exists(json_path):
        return None
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)

def pack_translations_to_bundle(items, bundle_path=None):
    """
    CacheFiles(__data)와 StreamingAssets(bundle) 양쪽 모두에 번역 내용을 패킹합니다.
    """
    mod_map = {}
    for it in items:
        if it.get('modified'):
            key = (it['table_id'], it['entry_id'], it['field_idx'])
            mod_map[key] = it['ko']

    print(f"[*] 총 수정 항목 수: {len(mod_map):,}개")

    # 우선 캐시 번들 원본 로드
    cache_src = CACHE_DATA + ".bak" if os.path.exists(CACHE_DATA + ".bak") else CACHE_DATA
    target_bundle_file = cache_src if os.path.exists(cache_src) else STREAMING_BUNDLE
    
    env = UnityPy.load(target_bundle_file)
    target_obj = None
    for obj in env.objects:
        if obj.type.name == 'TextAsset':
            raw = obj.get_raw_data()
            name_len = struct.unpack_from('<i', raw, 0)[0]
            name = raw[4:4+name_len].decode('utf-8', errors='ignore')
            if name == 'String_Korea':
                target_obj = obj
                break

    if not target_obj:
        raise ValueError("String_Korea 에셋을 찾을 수 없습니다.")

    raw_ko = extract_script(target_obj.get_raw_data())
    ko_tables = parse_protobuf_tables(raw_ko)

    # 수정 치환
    for table_id, entries in ko_tables.items():
        for entry in entries:
            eid = entry['id']
            for f_idx, f in enumerate(entry['fields']):
                key = (table_id, eid, f_idx)
                if key in mod_map:
                    f['val'] = mod_map[key]

    # Protobuf 바이너리 재인코딩
    rebuilt = bytearray()
    for fn in sorted(ko_tables.keys()):
        entries = ko_tables[fn]
        t_buf = bytearray()
        for entry in entries:
            e_buf = bytearray()
            for f in entry['fields']:
                if f['wire'] == 0:
                    e_buf += encode_varint(f['tag']) + encode_varint(f['val'])
                elif f['wire'] == 2:
                    s_bytes = f['val'].encode('utf-8')
                    e_buf += encode_varint(f['tag']) + encode_varint(len(s_bytes)) + s_bytes
            t_buf += bytes([10]) + encode_varint(len(e_buf)) + e_buf
        t_tag = (fn << 3) | 2
        rebuilt += encode_varint(t_tag) + encode_varint(len(t_buf)) + t_buf

    new_raw = make_textasset_raw("String_Korea", bytes(rebuilt))
    target_obj.set_raw_data(new_raw)
    target_obj.byte_size = len(new_raw)

    saved_bytes = env.file.save(packer="lz4")

    # 1. CacheFiles(__data)에 저장 (게임 실행 시 최우선 읽는 파일)
    if os.path.exists(CACHE_DIR):
        with open(CACHE_DATA, "wb") as f:
            f.write(saved_bytes)
        print(f"[+] 캐시 번들(__data) 패치 완료: {CACHE_DATA}")

    # 2. StreamingAssets(bundle)에 저장
    with open(STREAMING_BUNDLE, "wb") as f:
        f.write(saved_bytes)
    print(f"[+] StreamingAssets 번들 패치 완료: {STREAMING_BUNDLE}")

    # 3. 배포용 zip 업데이트
    dist_dir = os.path.join(BASE_DIR, "OverField_Korean_Patch")
    sa_target = os.path.join(dist_dir, "launcher_Data", "StreamingAssets", "yoo", "DefaultPackage")
    cache_target = os.path.join(dist_dir, "launcher_Data", "yoo", "DefaultPackage", "CacheFiles", "68", "68a9e72732e99edf100d6e4a6f692583")
    os.makedirs(sa_target, exist_ok=True)
    os.makedirs(cache_target, exist_ok=True)
    shutil.copy2(STREAMING_BUNDLE, os.path.join(sa_target, "d36af905d36461838e80ed5db5090c65.bundle"))
    shutil.copy2(CACHE_DATA, os.path.join(cache_target, "__data"))

    dist_zip = os.path.join(BASE_DIR, "OverField_Korean_Patch_v1.0.zip")
    with zipfile.ZipFile(dist_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(dist_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, dist_dir)
                zf.write(full_path, rel_path)

    return len(mod_map)
