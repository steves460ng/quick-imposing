# PR 009: 연속 붙여넣기 (Ctrl+Shift+V)

| 항목 | 내용 |
|---|---|
| 상태 | 병합됨 (2026-11-17, GitHub PR #21, 사용자 병합 지시) |
| 브랜치 | `claude/repeat-paste` → `main` |
| 기준 커밋 | main `c991dea` (0.7.0) |
| 최신 커밋 | 브랜치 최신 |
| 관련 문서 | [TEMPLATE-REQUIREMENTS](../docs/TEMPLATE-REQUIREMENTS.md) §6.5, [README](../README.md) §셀 복사와 붙여넣기, [UI-DESIGN](../docs/UI-DESIGN.md) |

> **작성 경위**: 2026-11-17 사용자 요청. "Ctrl+Shift+V를 누르면 반복 수량 입력 다이얼로그, 숫자만큼 붙여넣기. 방향은 정방향 · 역방향 설정과 같고, 마지막 셀이나 가로막는 셀을 만나면 경고 없이 멈춘다." 검토 후 사용자가 세부 규칙을 정했다(아래). 버전 0.8.0.

## 사용자 결정 (2026-11-17)

| 질문 | 결정 |
|---|---|
| 입력하는 숫자의 뜻 | 복사한 묶음의 **반복 횟수** |
| 복사한 빈칸 | 한 칸을 차지한다 |
| 반복 도중에 막힘 | 묶음 일부라도 들어가는 데까지 넣는다 |
| "경고 없이 멈춤" | 대화상자는 띄우지 않고 **기록 창에 경고 문구**를 남긴다 |
| 입력 상한 | 시작 셀부터 마지막 셀까지 남은 칸 수 |
| 붙여넣은 뒤 선택 셀 | 옮기지 않는다 |

## 구현 요약

- `Session.plan_repeat_paste(start_cell, items, times)`: 채움 순서로 묶음을 `times`번 펼쳐 놓으며, 데이터가 있는 셀 앞(`occupied`)이나 마지막 셀 뒤(`end_of_cells`)에서 멈춘다. 대체하지 않는다. 결과에 `targets`, `reason`, `blocked_cell`, `wanted`, `repeats`, `extra`. 적용은 기존 `apply_paste`.
- `Session.remaining_cells(start_cell)`: 입력 상한용.
- 작업 프로그램: `편집 → 연속 붙여넣기(&R)…`, 단축키 Ctrl+Shift+V(일반 붙여넣기와 같은 조건에서 켜짐). 정수 입력 창(기본 1, 1~남은 칸). 결과는 기록 창에 한 줄, 멈추면 `경고 — …` 한 줄. 대화상자 없음.
- 새 화면 문구는 `REPEAT_PASTE_TEXT` 표 한 곳에 이름 붙은 값 자리로 모았다(조사 조립 없음, `docs/HANDOFF-I18N.md` 규칙).

## 결과 요약

| 검증 | 결과 |
|---|---|
| `python -m pytest -q` | **148 passed** (새 테스트 12: `tests/test_repeat_paste.py`) |
| `test03_runner.py` / `test32_runner.py` | PASS / PASS |
| `ruff check --select F imposing tests` | 문제 없음 |
| 입력 창 화면 캡처 | 확인함 |

새 테스트: 반복 횟수 의미, 역방향, 빈칸이 한 칸 차지, 데이터 있는 셀 앞에서 멈춤과 묶음 일부, 마지막 셀에서 멈춤, 시작 셀이 막혀 있을 때, 새 셀의 겹침 순서, 남은 칸 수, 메뉴 · 단축키 · 활성 조건, 입력 창 값(기본 · 상한) · 기록 문구, 취소, 멈출 때 대화상자 없이 기록 창 경고.

Windows 검증 통과 (2026-11-17): [실행 43990081227](https://github.com/steves460ng/quick-imposing/actions/runs/43990081227)(`dca102a`) 전 단계 성공(pytest, 실행기, 한글 경로, GUI 시작 점검, 배포 빌드 · 라이선스 수집 · 시작 점검, PowerShell 5.1). 단축키 Ctrl+Shift+V의 실제 키 입력은 사용자 PC에서 확인할 항목이다(테스트는 단축키 설정과 동작 함수를 확인).

## 알아 둘 점

- 입력 창의 OK/Cancel 버튼은 영어로 나온다. Qt 기본 번역을 불러오지 않는 기존 문제이며 다국어 1단계(`docs/HANDOFF-I18N.md`)에서 함께 해결한다.
- 되돌리기 기능은 없다. 연속 붙여넣기는 빈 셀에만 넣으므로 `셀 비우기`로 바로잡을 수 있다.

---

## 검토

## 수정 내역

### 2026-11-17 메뉴 · 단축키로 실행하면 동작하지 않던 결함 (0.8.1)

사용자 보고: "연속 붙여넣기 메뉴만 있고 동작을 안 함. 다이얼로그도 안 뜸."

원인: `QAction.triggered`는 `checked`(False) 값을 넘긴다. 메뉴를 `repeat_paste_cells(times=None)`에 바로 연결해 `times=False`가 되었고, 입력 창을 건너뛴 뒤 `plan_repeat_paste`가 `ValueError`를 냈다. 창 프로그램이라 오류가 화면에 보이지 않았다. 테스트는 함수를 직접 불러 이 경로를 지나지 않았다.

수정: 메뉴를 `lambda: self.repeat_paste_cells()`로 연결. 메뉴 동작(`trigger()`)으로 입력 창이 뜨고 붙여넣기가 되는지 확인하는 회귀 테스트 추가(수정 전 실패, 수정 후 통과 확인). 같은 방식으로 연결된 다른 메뉴(`open_project`, `save_pdf`)는 `if not path`로 처리해 영향이 없다. 버전 0.8.1.

Windows 검증 통과: [실행 43995368847](https://github.com/steves460ng/quick-imposing/actions/runs/43995368847)(`4e9f1be`) 전 단계 성공. pytest 149 passed(Linux).
