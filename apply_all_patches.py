"""
통합 패치 주입 스크립트:
- String_Korea (스토리 대사 11,000줄) + Voice_Korea (보이스 자막 3,674줄)
- CacheFiles (__data 및 __info) 및 StreamingAssets (bundle) 양쪽 모두에 완벽하게 패킹
"""

import os
import sys
import json
import struct
import zlib
import shutil
import zipfile
import UnityPy

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
from game_paths import configured_game_dir, detect_yooasset_cache
_GAME_PATHS = detect_yooasset_cache(configured_game_dir())
STREAMING_BUNDLE = _GAME_PATHS['streaming_bundle']
CACHE_DIR = _GAME_PATHS['cache_dir']
CACHE_DATA = _GAME_PATHS['data_file']
CACHE_INFO = _GAME_PATHS['info_file']
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
    """
    유니티 텍스트에셋 바이너리 생성 (4바이트 정렬 패딩 필수)
    """
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

def parse_string_tables(data):
    tables = []
    offset = 0
    while offset < len(data):
        tag, offset = parse_varint(data, offset)
        fn = tag >> 3
        l, offset = parse_varint(data, offset)
        t_buf = data[offset:offset+l]
        offset += l
        entries = []
        sub_off = 0
        while sub_off < len(t_buf):
            _, sub_off = parse_varint(t_buf, sub_off)
            el, sub_off = parse_varint(t_buf, sub_off)
            eb = t_buf[sub_off:sub_off+el]
            sub_off += el
            io = 0
            fields = []
            while io < len(eb):
                itag, io = parse_varint(eb, io)
                iw = itag & 7
                ifn = itag >> 3
                if iw == 0:
                    v, io = parse_varint(eb, io)
                    fields.append({'tag': itag, 'wire': iw, 'fn': ifn, 'val': v})
                elif iw == 2:
                    sl, io = parse_varint(eb, io)
                    s_raw = eb[io:io+sl]
                    io += sl
                    fields.append({'tag': itag, 'wire': iw, 'fn': ifn, 'val': s_raw.decode('utf-8', errors='ignore')})
                else:
                    break
            entries.append(fields)
        tables.append((fn, entries))
    return tables

def encode_string_tables(tables):
    rebuilt = bytearray()
    for fn, entries in tables:
        t_buf = bytearray()
        for fields in entries:
            e_buf = bytearray()
            for f in fields:
                if f['wire'] == 0:
                    e_buf += encode_varint(f['tag']) + encode_varint(f['val'])
                elif f['wire'] == 2:
                    s_bytes = f['val'].encode('utf-8')
                    e_buf += encode_varint(f['tag']) + encode_varint(len(s_bytes)) + s_bytes
            t_buf += bytes([10]) + encode_varint(len(e_buf)) + e_buf
        t_tag = (fn << 3) | 2
        rebuilt += encode_varint(t_tag) + encode_varint(len(t_buf)) + t_buf
    return bytes(rebuilt)

def generate_info_file(bundle_bytes):
    """
    YooAsset 2.0 __info 바이너리 생성:
    - 2 bytes short: string length (8)
    - 8 bytes ASCII: CRC32 string in lowercase hex (e.g. 'f6948d0e')
    - 8 bytes int64: File length in bytes (little-endian)
    Total 18 bytes.
    """
    crc = zlib.crc32(bundle_bytes) & 0xffffffff
    crc_str = f'{crc:08x}'.encode('ascii')
    size = len(bundle_bytes)
    return struct.pack('<H', 8) + crc_str + struct.pack('<q', size)

def apply_all():
    print("[*] translations.json 로드 중...")
    with open(WORK_JSON, "r", encoding="utf-8") as f:
        items = json.load(f)

    # 수정 맵 구성: (table_id, entry_id, field_idx) -> new_text
    mod_map = {}
    for it in items:
        if it.get('modified'):
            key = (it['table_id'], it['entry_id'], it['field_idx'])
            mod_map[key] = it['ko']

    print(f"[*] 적용할 String_Korea 수정 항목 수: {len(mod_map):,}개")

    # 원본 핫픽스 캐시 번들 로드
    cache_src = CACHE_DATA + ".clean_orig" if os.path.exists(CACHE_DATA + ".clean_orig") else CACHE_DATA
    print(f"[*] 캐시 번들 로드 중: {cache_src}")
    env = UnityPy.load(cache_src)

    sk_obj = None
    vk_obj = None

    for obj in env.objects:
        if obj.type.name == 'TextAsset':
            raw = obj.get_raw_data()
            name_len = struct.unpack_from('<i', raw, 0)[0]
            name = raw[4:4+name_len].decode('utf-8', errors='ignore')
            if name == 'String_Korea':
                sk_obj = obj
            elif name == 'Voice_Korea':
                vk_obj = obj

    if not sk_obj:
        print("[-] String_Korea를 찾을 수 없습니다.")
        return

    # 1. String_Korea 패치
    sk_raw = extract_script(sk_obj.get_raw_data())
    sk_tables = parse_string_tables(sk_raw)

    applied_sk = 0
    for fn, entries in sk_tables:
        for entry in entries:
            eid = None
            for f in entry:
                if f['fn'] == 1 and f['wire'] == 0:
                    eid = f['val']
                    break
            if eid is not None:
                for f_idx, f in enumerate(entry):
                    k = (fn, eid, f_idx)
                    if k in mod_map:
                        f['val'] = mod_map[k]
                        applied_sk += 1

    print(f"[+] String_Korea에 {applied_sk:,}개 문장 치환 완료")
    new_sk_script = encode_string_tables(sk_tables)
    new_sk_raw = make_textasset_raw("String_Korea", new_sk_script)
    sk_obj.set_raw_data(new_sk_raw)
    sk_obj.byte_size = len(new_sk_raw)

    # 2. Voice_Korea 패치 (기존 auto_translate_voice에서 번역된 최신 데이터가 있다면 주입)
    str_bundle_path = STREAMING_BUNDLE
    if os.path.exists(str_bundle_path):
        try:
            str_env = UnityPy.load(str_bundle_path)
            for sobj in str_env.objects:
                if sobj.type.name == 'TextAsset':
                    s_raw = sobj.get_raw_data()
                    name_len = struct.unpack_from('<i', s_raw, 0)[0]
                    name = s_raw[4:4+name_len].decode('utf-8', errors='ignore')
                    if name == 'Voice_Korea' and vk_obj:
                        vk_script = extract_script(s_raw)
                        new_vk_raw = make_textasset_raw("Voice_Korea", vk_script)
                        vk_obj.set_raw_data(new_vk_raw)
                        vk_obj.byte_size = len(new_vk_raw)
                        print("[+] Voice_Korea(음성 자막) 최신 번역본 동시 주입 완료")
                        break
        except Exception as e:
            print(f"[-] Voice_Korea 주입 경고: {e}")

    # 3. 캐시 파일(__data)에 저장 (게임이 실제로 우선 읽는 파일!)
    print(f"[*] 캐시 번들 저장 중: {CACHE_DATA}")
    saved_bytes = env.file.save(packer='lz4')
    with open(CACHE_DATA, "wb") as f:
        f.write(saved_bytes)
    print(f"[+] 캐시 번들(__data) 저장 성공! ({len(saved_bytes):,} bytes)")

    # 4. YooAsset 검증 파일(__info) 업데이트 (중요! CRC 및 파일 크기 불일치 시 YooAsset이 원본을 재다운로드함)
    info_bytes = generate_info_file(saved_bytes)
    with open(CACHE_INFO, "wb") as f:
        f.write(info_bytes)
    print(f"[+] 캐시 메타데이터(__info) 동기화 완료! ({len(info_bytes)} bytes)")

    # 5. StreamingAssets 쪽 번들에도 동일하게 저장 (클린 설치 유저용)
    print(f"[*] StreamingAssets 번들 저장 중: {STREAMING_BUNDLE}")
    with open(STREAMING_BUNDLE, "wb") as f:
        f.write(saved_bytes)
    print(f"[+] StreamingAssets 번들 저장 성공!")

    # 6. 배포용 패키지 업데이트
    print("[*] 배포용 패키지 파일 업데이트 중...")
    dist_dir = os.path.join(BASE_DIR, "OverField_Korean_Patch")

    # 6-1. StreamingAssets 경로
    sa_target = os.path.join(dist_dir, "launcher_Data", "StreamingAssets", "yoo", "DefaultPackage")
    os.makedirs(sa_target, exist_ok=True)
    shutil.copy2(STREAMING_BUNDLE, os.path.join(sa_target, "d36af905d36461838e80ed5db5090c65.bundle"))

    # 6-2. CacheFiles 경로 (__data + __info 필수!)
    cache_target = os.path.join(dist_dir, "launcher_Data", "yoo", "DefaultPackage", "CacheFiles", "68", "68a9e72732e99edf100d6e4a6f692583")
    os.makedirs(cache_target, exist_ok=True)
    shutil.copy2(CACHE_DATA, os.path.join(cache_target, "__data"))
    shutil.copy2(CACHE_INFO, os.path.join(cache_target, "__info"))

    # zip 생성
    dist_zip = os.path.join(BASE_DIR, "OverField_Korean_Patch_v1.0.zip")
    with zipfile.ZipFile(dist_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(dist_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, dist_dir)
                zf.write(full_path, rel_path)

    print(f"[+] 배포용 압축 파일({dist_zip}) 업데이트 완료!")

if __name__ == "__main__":
    apply_all()
