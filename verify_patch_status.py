# -*- coding: utf-8 -*-
import os
import sys
import zlib
import struct
import binascii
import UnityPy
from game_paths import configured_game_dir, detect_yooasset_cache

sys.stdout.reconfigure(encoding='utf-8')

print("=== OverField 패치 데이터 검증 보고서 ===")

# 1. 활성 캐시 경로 확인
cache_info = detect_yooasset_cache(configured_game_dir())
print(f"1. YooAsset 활성 해시: {cache_info['cache_hash']}")
print(f"   - 캐시 번들 파일(__data): {cache_info['data_file']}")
print(f"   - 캐시 메타 파일(__info): {cache_info['info_file']}")
print(f"   - 스트리밍 번들: {cache_info['streaming_bundle']}")

data_file = cache_info['data_file']
info_file = cache_info['info_file']

if os.path.exists(data_file) and os.path.exists(info_file):
    data_bytes = open(data_file, 'rb').read()
    info_bytes = open(info_file, 'rb').read()

    actual_crc = binascii.crc32(data_bytes) & 0xFFFFFFFF
    crc_hex = f"{actual_crc:08x}".upper()

    # info 파싱
    slen = struct.unpack_from('<H', info_bytes, 0)[0]
    stored_crc = info_bytes[2:2+slen].decode('ascii').upper()
    stored_size = struct.unpack_from('<q', info_bytes, 2+slen)[0]

    print(f"\n2. 무결성 검증:")
    print(f"   - __data 실제 크기: {len(data_bytes):,} bytes | __info 기록 크기: {stored_size:,} bytes")
    print(f"   - __data 실제 CRC32: {crc_hex} | __info 기록 CRC32: {stored_crc}")

    if crc_hex == stored_crc and len(data_bytes) == stored_size:
        print("   ✅ YooAsset 무결성 100% 일치 (게임 실행 시 통과 보장)")
    else:
        print("   ❌ 무결성 불일치!")
else:
    print("❌ 캐시 파일 없음!")

# 3. TextAsset 내용 확인
print(f"\n3. 번들 내 텍스트 에셋 검증:")
env = UnityPy.load(data_file)
for obj in env.objects:
    if obj.type.name == 'TextAsset':
        raw = obj.get_raw_data()
        nl = struct.unpack_from('<i', raw, 0)[0]
        name = raw[4:4+nl].decode('utf-8', errors='ignore')
        print(f"   - TextAsset: {name:15} ({len(raw):,} bytes)")

# 4. 배포 아티팩트 크기 확인
print(f"\n4. 배포 아티팩트 현황:")
for f in ["patch_payload.dat", "OverField_Korean_Patch_v1.0.zip", "OverFieldLauncher.exe", "OverField_Translation_Tables.xlsx"]:
    if os.path.exists(f):
        print(f"   - {f:32} : {os.path.getsize(f):,} bytes")
    else:
        print(f"   - {f:32} : 없음")
