# PR 008: MIT 라이선스와 서드파티 라이선스 고지

| 항목 | 내용 |
|---|---|
| 상태 | 검토 대기 |
| 브랜치 | `claude/license` → `main` |
| 기준 커밋 | main `073aba3` (0.7.0) |
| 최신 커밋 | 브랜치 최신 |
| 관련 문서 | [README](../README.md) §라이선스 · §라이선스와 서드파티 고지, [packaging/collect_licenses.py](../packaging/collect_licenses.py) |

> **작성 경위**: 2026-11-16 저장소 공개를 앞두고 사용자가 정했다. "MIT로 하고 저작권자는 steves460ng. 서드파티 라이선스도 포함." 프로그램 동작 변경은 없으므로 버전은 그대로 0.7.0이다.

## 구현 요약

- `LICENSE`: MIT, `Copyright (c) 2026 steves460ng`. `pyproject.toml`에 `license = "MIT"`, `license-files = ["LICENSE"]`(PEP 639, setuptools 77 이상 필요로 올림).
- `packaging/collect_licenses.py`: 배포 폴더의 `THIRD-PARTY-LICENSES\`를 만든다.
  - Python 패키지: `quick-imposing[gui]`의 실행 의존성 전체(환경 표지 반영)와 PyInstaller(부트로더가 exe에 들어감). 각 패키지 메타데이터의 라이선스 파일을 복사한다. `*.dist-info/licenses/` 아래는 전부 복사해, pikepdf가 함께 넣은 qpdf · zlib · OpenSSL · libjpeg-turbo 등의 문서도 들어간다.
  - 라이선스 파일이 없는 패키지(PySide6 · shiboken6)는 `packaging/licenses/`의 표준 문서(LGPL-3.0, GPL-3.0)를 넣는다.
  - Python 런타임 라이선스(`LICENSE.txt`).
  - qpdf · Poppler: 실행 파일 폴더와 `tools\`의 내려받은 배포 폴더에서 LICENSE/COPYING/NOTICE 류 파일을 찾아 복사하고, 표준 문서(Apache-2.0 / GPL-2.0 · GPL-3.0)를 함께 넣는다. 버전은 실행해서 읽는다.
  - `README.md`: 구성 요소 · 버전 · 라이선스 · 문서 위치 표, Poppler 소스 안내, Qt LGPL 안내.
  - 라이선스 문서가 하나도 없는 구성 요소는 경고(빌드 계속)하고, 표에 "라이선스 문서 없음"과 원문 주소(PyPI 등)를 적는다. `--strict`(`build.ps1 -StrictLicenses`)이면 종료 코드 1.
- `packaging/licenses/`: Apache-2.0, GPL-2.0, GPL-3.0, LGPL-3.0 표준 전문.
- `packaging/build.ps1`: 배포 폴더에 `LICENSE.txt`를 넣고 위 스크립트를 실행한다. 시작 점검의 필수 파일 목록에 `LICENSE.txt`, `THIRD-PARTY-LICENSES\README.md` 추가.
- README: 사용자 부분에 "라이선스" 절, 개발 부분에 "라이선스와 서드파티 고지".

## 결과 요약

| 검증 | 결과 |
|---|---|
| `python -m pytest -q` | **136 passed** (새 테스트 5: `tests/test_licenses.py`) |
| `ruff check --select F imposing tests packaging/collect_licenses.py` | 문제 없음 |
| Linux에서 스크립트 실행 | 구성 요소 10개, 모두 라이선스 문서 있음 |

Windows 검증: 병합 전에 `windows` 워크플로를 수동 실행한다. 이 변경은 `build.ps1`을 바꾸므로 워크플로의 배포 빌드 단계가 실제 검증이다.

## 알아 둘 점

- 이 세션에서는 qpdf · Poppler의 Windows 배포 zip을 내려받을 수 없어, 그 안에 어떤 라이선스 파일이 있는지는 확인하지 못했다. 찾지 못해도 표준 문서는 항상 들어간다. Windows 빌드 후 `THIRD-PARTY-LICENSES\README.md`의 표를 한 번 확인한다.
- Poppler Windows 빌드에 함께 든 라이브러리(cairo, freetype 등)의 라이선스는 zip에 문서가 있으면 복사되고, 없으면 poppler-windows 저장소 안내로 대신한다.
- `THIRD-PARTY-LICENSES\README.md`의 "소스가 필요하면 Issues로 요청" 문장은 GPL 바이너리를 배포하는 쪽(저장소 주인)의 소스 제공 약속이다.
- 법률 자문이 아니다. 회사 이름으로 외부 배포한다면 회사 정책을 확인한다.

---

## 검토

## 수정 내역

### 2026-11-16 Windows에서 Qt 라이선스가 상용 라이선스 문서만 들어간 문제

Windows 워크플로 [43841936581](https://github.com/steves460ng/quick-imposing/actions/runs/43841936581) · [43842819521](https://github.com/steves460ng/quick-imposing/actions/runs/43842819521)에서 pytest가 실패했다(배포 빌드 단계는 통과). Windows용 PySide6 · shiboken6 패키지에는 Linux용과 달리 `LicenseRef-Qt-Commercial.txt`(Qt 상용 라이선스) 한 파일이 들어 있어, 표준 LGPL 문서를 넣는 조건(문서가 하나도 없을 때)에 걸리지 않았다. 그래서 배포본에 Qt 상용 라이선스만 들어가고 실제로 쓰는 LGPL 문서가 빠졌다.

수정: 라이선스 표현에 LGPL-3.0이 있는 패키지는 패키지가 넣은 문서와 관계없이 LGPL-3.0 · GPL-3.0 표준 문서를 항상 넣는다. 이 배포본에 해당하지 않는 `LicenseRef-*Commercial*` 문서는 복사하지 않는다. Windows 패키지 구성을 흉내 낸 테스트 추가.

이 실행에서 확인한 Windows 빌드 결과(빌드 단계 출력): 구성 요소 16개(altgraph, fonttools, lxml, packaging, pefile, pikepdf 13개 문서, pillow, pyinstaller, pyinstaller-hooks-contrib, PySide6_Essentials, pywin32-ctypes, setuptools, shiboken6, Python 3.12.10, qpdf 12.4.2, Poppler 26.09.0), 경고 없음. qpdf · Poppler는 내려받은 배포 파일에서 각각 라이선스 문서 1개를 찾았고 표준 문서가 함께 들어갔다. PyInstaller의 빌드용 의존성(altgraph, pefile, setuptools 등)도 목록에 들어가는데, 실제로 exe에 들어가지 않는 것까지 넣는 쪽이라 고지가 모자랄 일은 없다.

### 2026-11-16 문서가 없는 구성 요소: 실패 → 경고

사용자 검토: "라이선스가 없다고 빌드가 안 되는 건 문제 아닌가." 메타데이터에 라이선스 이름만 있고 문서를 넣지 않은 패키지가 의존성에 새로 들어오면, 코드와 관계없이 배포본을 못 만들게 된다. MIT · BSD는 저작권자 줄이 필요해 표준 문서로 대신할 수도 없다. 그래서 기본은 경고(빌드 계속, 표에 "라이선스 문서 없음"과 원문 주소)로 바꾸고, 외부 배포 전 확인용으로 `build.ps1 -StrictLicenses`(`--strict`)를 두었다. 경고는 표준 출력으로 낸다(Windows PowerShell은 외부 명령의 표준 오류를 오류로 다룰 수 있음). 테스트 1개 추가.
