# PR 010: 쓰지 않는 파일 정리

| 항목 | 내용 |
|---|---|
| 상태 | 병합됨 (2026-11-17, GitHub PR #23, 사용자 병합 지시) |
| 브랜치 | `claude/cleanup` → `main` |
| 기준 커밋 | main `6cf2236` (0.8.1) |
| 최신 커밋 | 브랜치 최신 |

> **작성 경위**: 2026-11-17 사용자 요청. "중간정리를 하자. 레포지토리에 지금은 안 쓰는 파일들이 있는지 확인해서 삭제해." 코드 · 동작 변경 없음.

## 삭제한 파일

| 파일 | 이유 | 확인 |
|---|---|---|
| `samples/templates/t2-*.json` (7개) | 2차 테스트 픽스처. 지금은 쓰지 않는 `template@1` 형식 | 코드 · 테스트 · 워크플로 · 빌드에서 참조 없음. `docs/TEST-02.md`만 참조 |
| `samples/expected/t2-*.expected.json` (7개) | 위 픽스처의 기대값 | 같음 |
| `docs/TEST-02.md` | 2차 테스트 명세. 2026-11-11에 "대체됨, 기록용"으로 표시. 픽스처가 없어지면 기록으로도 쓸 수 없음 | 다른 문서의 언급 7곳을 "2026-11-17 삭제, 내용은 커밋 `2d84f9c`" 표기로 바꿈 |
| `requirements.txt` | `pyproject.toml`과 중복이고 PySide6가 빠져 있어 그대로 쓰면 GUI가 설치되지 않음. 설치 · CI · 빌드 모두 `pip install -e ".[test,gui]"` 사용 | 참조 없음 |

이전 핸드오프의 미결 항목 "2차 픽스처 삭제 여부"가 이것으로 정리된다.

## 검토했지만 남긴 파일

| 파일 | 남긴 이유 |
|---|---|
| `samples/input/base.pdf`, `B-1~3.pdf` | 3-1차 · 3-2차 실행기와 테스트 픽스처가 쓴다 |
| `docs/HANDOFF-2026-11-10~13.md` | 11-11은 목표 · 제약 · 결정의 기준으로, 11-13은 빌드 절차로 다른 문서가 참조한다 |
| `docs/TASK-03-*.md`, `TEST-03-*-RESULTS.md` | 실행기가 따르는 테스트 명세와 결과 |
| `docs/CLI-TEST-GUIDE.md`, `samples/manual/` | 명령행 직접 확인 안내. `samples/manual/`은 테스트가 쓴다 |
| `packaging/make_icons.py` | 아이콘을 다시 만들 때 쓰는 도구 |
| `PR/*.md` | 기록은 지우지 않는다는 규칙(`PR/README.md`) |

## 문서 반영

- `docs/SPEC.md` v0.7.1: §10 저장소 구조에서 삭제한 항목을 빼고, `base.pdf` 설명을 현재 쓰임에 맞게 고침. 변경 이력 추가.
- `docs/TASK-03-1.md`, `docs/TEMPLATE-REQUIREMENTS.md`: `TEST-02.md` 언급에 삭제 표기.
- `docs/HANDOFF-2026-11-16.md` §3-5에 정리 완료 기록.

## 결과 요약

| 검증 | 결과 |
|---|---|
| `python -m pytest -q` | 149 passed |
| `test03_runner.py` / `test32_runner.py` | PASS / PASS |
| 남은 참조 검색 | 삭제한 파일을 가리키는 곳 없음(삭제 표기 제외) |

---

## 검토

## 수정 내역
