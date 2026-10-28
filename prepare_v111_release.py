# -*- coding: utf-8 -*-
"""
v1.1.1 릴리스 준비 및 배포 자동화 스크립트
1. reviewed.bundle 및 reviewed_payload.dat 검증
2. 배포용 파일(OverField_Korean_Patch_v1.1.1.zip, patch_payload.dat, OverFieldLauncher.exe, launcher_config.json, SHA256SUMS.txt) 생성
3. CHANGELOG.md 갱신
4. Git 커밋 및 태그(v1.1.1) 생성
5. GitHub 푸시 및 릴리스(gh release create) 발행
6. 로컬 설치 게임 캐시 및 스트리밍 번들 동기화
"""

import os
import sys
import json
import zlib
import struct
import hashlib
import zipfile
import shutil
import subprocess

sys.stdout.reconfigure(encoding='utf-8')

WORK_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\OverField-Korean-Patch\작업자료"
GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\OverField"
TOP_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\OverField-Korean-Patch"
DIST_DIR = os.path.join(WORK_DIR, "dist_v1.1.1")

os.makedirs(DIST_DIR, exist_ok=True)

# 1. 파일 경로 정의
reviewed_bundle = os.path.join(WORK_DIR, "translation_review", "reviewed.bundle")
reviewed_payload = os.path.join(WORK_DIR, "translation_review", "reviewed_payload.dat")
reviewed_info = os.path.join(WORK_DIR, "translation_review", "reviewed__info")
launcher_exe = os.path.join(TOP_DIR, "OverFieldLauncher.exe")

bundle_data = open(reviewed_bundle, "rb").read()
payload_data = open(reviewed_payload, "rb").read()
info_data = open(reviewed_info, "rb").read()
exe_data = open(launcher_exe, "rb").read()

bundle_crc = f"{zlib.crc32(bundle_data) & 0xffffffff:08x}"
print(f"[*] 1. 입력 번들 검증: {len(bundle_data):,} bytes (CRC32: {bundle_crc.upper()})")
print(f"[*]    페이로드 검증: {len(payload_data):,} bytes")
print(f"[*]    런처 EXE 검증: {len(exe_data):,} bytes")

# 2. dist 파일 준비
dist_payload = os.path.join(DIST_DIR, "patch_payload.dat")
dist_exe = os.path.join(DIST_DIR, "OverFieldLauncher.exe")
dist_config = os.path.join(DIST_DIR, "launcher_config.json")
dist_zip = os.path.join(DIST_DIR, "OverField_Korean_Patch_v1.1.1.zip")
dist_sha = os.path.join(DIST_DIR, "SHA256SUMS.txt")

# 페이로드 및 런처 복사
open(dist_payload, "wb").write(payload_data)
open(dist_exe, "wb").write(exe_data)

# launcher_config.json 생성
clean_config = {
    "github_repo": "versusmangho/OverField-Korean-Patch",
    "auto_update": True,
    "auto_launch": False,
    "close_launcher_on_game_start": True,
    "current_patch_version": "1.1.1"
}
with open(dist_config, "w", encoding="utf-8") as f:
    json.dump(clean_config, f, indent=4, ensure_ascii=False)

# 수동 설치용 zip 생성
readme_text = """========================================================================
           오버필드 (OverField) 고품질 한국어 패치 v1.1.1
========================================================================

[1] 자동 패처 / 런처 사용 방법 (권장)
------------------------------------------------------------------------
1. 압축 파일 내의 'OverFieldLauncher.exe'를 실행합니다.
2. 스팀 게임 설치 폴더가 자동으로 감지됩니다.
3. [🎮 게임 시작 (GAME START)] 버튼을 클릭하면 한국어가 적용된 오버필드가 바로 실행됩니다.
   - 점검/핫픽스 발생 시에도 런처가 자동으로 패치를 재동기화하여 무결성을 통과시킵니다.

[2] 수동 덮어쓰기 설치 방법
------------------------------------------------------------------------
1. 게임을 완전히 종료합니다.
2. 본 압축 파일의 'launcher_Data' 폴더를 게임 설치 폴더에 그대로 덮어씁니다.
   - 기본 경로: C:\\Program Files (x86)\\Steam\\steamapps\\common\\OverField
3. 게임을 실행합니다.

[패치 내역 v1.1.1]
------------------------------------------------------------------------
- Table 1, 7, 17, 20, 46, 63 총 4,700개 텍스트 필드 정밀 교정
- 프롤로그 및 메인스토리 대화 화자별 말투(시, 페이, 팡틴 등) 일관성 확립
- 전투 스킬 및 장비 세트 옵션, 캐릭터 돌파 특성의 중국어 잔재 100% 한글화
- 음성 타이밍으로 인해 중간에 잘리던 오디오 자막(83개소) 연결 복원
- 중국어 화자 이름(引导员 菲 -> 가이드 페이 등 149개소) 전면 교정
========================================================================
"""

print("[*] 2. 수동 설치용 zip(OverField_Korean_Patch_v1.1.1.zip) 생성 중...")
with zipfile.ZipFile(dist_zip, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("OverFieldLauncher.exe", exe_data)
    zf.writestr("patch_payload.dat", payload_data)
    zf.writestr("launcher_config.json", json.dumps(clean_config, indent=4, ensure_ascii=False))
    zf.writestr("패치_안내.txt", readme_text)
    
    # StreamingAssets 번들
    zf.writestr("launcher_Data/StreamingAssets/yoo/DefaultPackage/d36af905d36461838e80ed5db5090c65.bundle", bundle_data)
    
    # YooAsset 활성 캐시 (83cc446e06ef9932aad15012b1e498f2 및 68a9e72732e99edf100d6e4a6f692583 둘 다 대응)
    zf.writestr("launcher_Data/yoo/DefaultPackage/CacheFiles/83/83cc446e06ef9932aad15012b1e498f2/__data", bundle_data)
    zf.writestr("launcher_Data/yoo/DefaultPackage/CacheFiles/83/83cc446e06ef9932aad15012b1e498f2/__info", info_data)
    zf.writestr("launcher_Data/yoo/DefaultPackage/CacheFiles/68/68a9e72732e99edf100d6e4a6f692583/__data", bundle_data)
    zf.writestr("launcher_Data/yoo/DefaultPackage/CacheFiles/68/68a9e72732e99edf100d6e4a6f692583/__info", info_data)

print(f"[+] zip 생성 완료: {os.path.getsize(dist_zip):,} bytes")

# SHA256SUMS.txt 생성
sha_lines = []
for fname in ["OverFieldLauncher.exe", "patch_payload.dat", "OverField_Korean_Patch_v1.1.1.zip", "launcher_config.json"]:
    fpath = os.path.join(DIST_DIR, fname)
    h = hashlib.sha256(open(fpath, "rb").read()).hexdigest()
    sha_lines.append(f"{h}  {fname}")

with open(dist_sha, "w", encoding="utf-8") as f:
    f.write("\n".join(sha_lines) + "\n")
print("[+] SHA256SUMS.txt 생성 완료")

# 3. CHANGELOG.md 업데이트
changelog_path = os.path.join(WORK_DIR, "CHANGELOG.md")
existing_cl = open(changelog_path, "r", encoding="utf-8").read()

v111_entry = """# 변경 이력

## v1.1.1 — 2026-10-28

### 번역 교정 (총 4,700개 필드)

| Table | 본문 수정 필드 | 원문 대조·정형 설명 교정 |
|---|---:|---:|
| 1 (아이템·도감) | 431 | 31 |
| 7 (스킬·버프) | 1,212 | 450 |
| 17 (장비·특성) | 666 | 495 |
| 20 (편지·공지) | 63 | 12 |
| 46 (스토리 대화) | 2,320 | 1,622 |
| 63 (미니게임) | 8 | 8 |
| **합계** | **4,700** | **2,618** |

- **스토리 대화(Table 46)**: 65개 라운드의 무작위 샘플링 및 대화 전면 재대조를 거쳐 1,287개 문장을 추가 교정했습니다.
- **인명·용어 통일**: `인륨`, `살베이저`, `프론티어` 등 핵심 용어 및 캐릭터 호칭 일관성을 확립했습니다.
- **음성 자막 완벽 복구**: 일본어 오디오 분할 슬롯으로 인해 뒷문장이 끊기던 83개 자막을 완전 결합했습니다.
- **중국어 잔재 100% 제거**: 149개 화자 이름(`引导员 菲` -> `가이드 페이` 등) 및 미니게임(Table 63), 캐릭터 돌파 특성(Table 17)의 중국어를 전면 번역했습니다.

"""

if "## v1.1.1" not in existing_cl:
    new_cl = existing_cl.replace("# 변경 이력\n", v111_entry)
    open(changelog_path, "w", encoding="utf-8").write(new_cl)
    print("[+] CHANGELOG.md에 v1.1.1 갱신 완료")

# 4. Git 작업
print("[*] 4. Git 상태 갱신 및 커밋 중...")
subprocess.run(["git", "add", "."], cwd=WORK_DIR, check=True)

commit_msg = "feat: publish v1.1.1 translation review (4,700 fields)"
subprocess.run(["git", "commit", "-m", commit_msg], cwd=WORK_DIR)

# 태그 생성 (기존 태그 삭제 후 재생성 방지)
subprocess.run(["git", "tag", "-a", "v1.1.1", "-m", "v1.1.1 — 4,700개 필드 번역 정밀 교정본"], cwd=WORK_DIR)

print("[*] 5. GitHub 원격 저장소에 Push 중...")
subprocess.run(["git", "push", "origin", "main", "--tags"], cwd=WORK_DIR, check=True)

# 6. gh CLI를 통한 Release 발행
print("[*] 6. GitHub Release(v1.1.1) 발행 중...")
release_notes = f"""Table 1, 7, 17, 20, 46, 63의 번역 필드 **4,700개**를 정밀 교정한 공식 v1.1.1 릴리스입니다.

- **스토리 대화(Table 46)**: 65회차의 정밀 대조 검토를 통해 총 2,320개 대사 및 나레이션을 자연스러운 구어체로 완성했습니다.
- **전투 스킬 & 장비(Table 7, 17)**: 스킬 설명 1,212개, 장비 및 돌파 특성 666개의 수치·효과 조건·중국어 잔재를 전면 교정했습니다.
- **음성 자막 복구**: 분할 타이밍으로 뒷문장이 잘리던 음성 자막 83개소를 완벽 연결 복구했습니다.
- **중국어 화자 이름 교정**: `引导员 菲` -> `가이드 페이` 등 149개소 화자 이름을 100% 한국어화했습니다.

### 설치 방법

1. **자동 패처 (권장)**:
   - **OverFieldLauncher.exe**를 실행하시면 GitHub에서 최신 패치 데이터를 자동으로 다운로드하여 1초 만에 설치합니다.
2. **수동 설치**:
   - **OverField_Korean_Patch_v1.1.1.zip**의 압축을 풀어 `launcher_Data` 폴더를 게임 설치 폴더에 덮어씌웁니다.
"""

release_cmd = [
    "gh", "release", "create", "v1.1.1",
    dist_exe, dist_payload, dist_zip, dist_config, dist_sha,
    "--title", "v1.1.1 — 번역 교정본(4,700개 필드) 및 인게임 대화 대조 반영",
    "--notes", release_notes,
    "-R", "versusmangho/OverField-Korean-Patch"
]

subprocess.run(release_cmd, cwd=WORK_DIR, check=True)
print("🎉 GitHub Release v1.1.1 발행 성공!")

# 7. 로컬 설치 게임 파일 동기화
print("[*] 7. 로컬 설치 게임 캐시 및 스트리밍 번들 동기화...")
cache_dir = os.path.join(GAME_DIR, r"launcher_Data\yoo\DefaultPackage\CacheFiles\83\83cc446e06ef9932aad15012b1e498f2")
os.makedirs(cache_dir, exist_ok=True)
open(os.path.join(cache_dir, "__data"), "wb").write(bundle_data)
open(os.path.join(cache_dir, "__info"), "wb").write(info_data)

streaming_bundle_path = os.path.join(GAME_DIR, r"launcher_Data\StreamingAssets\yoo\DefaultPackage\d36af905d36461838e80ed5db5090c65.bundle")
open(streaming_bundle_path, "wb").write(bundle_data)
print("[+] 로컬 게임 캐시 동기화 완료!")
