# quick-imposing

명함 같은 카드 PDF를 인쇄용 판 PDF의 정해진 칸에 배치하는 Windows 프로그램(Python + PySide6, pikepdf, qpdf·Poppler).
작업 프로그램(`imposing/gui/work.py`)과 템플릿 편집기(`imposing/gui/editor.py`), 배치 엔진(`imposing/engine.py`)으로 되어 있다. 규칙은 `docs/SPEC.md`, 사용법은 `README.md`.

## 작업 방식
- 주 업무는 기획·분석·설계·문서·검토다. **코드 작성·수정은 사용자가 지시할 때만** 한다. 답은 한국어로.
- 작업 브랜치에서 커밋 → push → GitHub PR → 병합. 브랜치는 세션이 정한 것을 쓰고, 없으면 `claude/<이름>`.
- **변경 기록은 PR 설명에 쓴다**: 작성 경위, 사용자 결정, 구현 요약, 검증 결과, 알아 둘 점.
- 병합은 사용자가 지시할 때만, merge commit으로 한다.
- 화면·리포트가 바뀌면 `pyproject.toml` 버전을 올린다(기능 추가는 둘째 자리, 수정은 셋째 자리).
- 사용자는 1차 베타 테스트 중이다. 화면이 바뀌는 변경은 미리 알리고 합의한다.
- 시각은 한국시간(KST, UTC+9)으로 알린다.

## 세션
- 시작하면 가장 최근 `docs/HANDOFF-*.md`를 먼저 읽는다. 저장소 전체 탐색은 필요할 때만 한다.
- 같은 주제로 이어지는 일은 한 세션에서 해도 된다. 주제가 바뀌면(예: 검토를 마치고 구현을 시작할 때) 새 세션을 권한다.
- 큰 단계가 끝나면 필요할 때 `docs/HANDOFF-<날짜>.md`를 남긴다.

## 검사
- `python scripts/check.py`: 전체(ruff F, pytest, 3-2차 실행기(3-1차 포함), GUI 시작 점검). 약 2분. PR 전에 돌린다.
- `python scripts/check.py <경로>...`: 그 경로의 ruff와 관련된 pytest만. 작업 중에는 이것을 쓴다.
- 성공하면 한 줄, 실패하면 실패 부분만 나온다. 전체 로그가 필요할 때만 pytest를 직접 돌린다.

## CI
- `ci.yml`(Linux): PR과 main push에서 검사 전체 실행. 문서만 바뀌면 건너뛴다.
- `windows.yml`: push 트리거는 `ccr-**`, `release/**`뿐이다. `claude/**` 브랜치는 수동 실행(`workflow_dispatch`)한다. 약 6분, 늦게 시작하기도 한다.
- **Linux에서 통과해도 Windows 결과를 확인한 뒤 병합한다.** Windows와 Linux 패키지가 다를 수 있다.
- CI 결과는 GitHub MCP 도구로 확인한다(`actions_list`, `get_job_logs`). `gh` CLI는 검색에만 쓴다.

## 이 세션 환경(Linux 클라우드) 준비
```sh
pip install -e '.[test,gui]' ruff==0.16.9
apt-get install -y qpdf poppler-utils fonts-noto-cjk libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3
export QT_QPA_PLATFORM=offscreen
python scripts/check.py
```
- 이 환경에서는 GitHub의 다른 저장소 배포 파일(qpdf, poppler-windows 등)을 내려받을 수 없다. Windows 배포 파일 내용은 워크플로 로그로 확인한다.

## 지킬 것
- 인쇄 색은 중요하다. 결과 PDF의 색에 영향을 줄 수 있는 변경이나 색 문제 조사는 먼저 `docs/COLOR.md`를 읽고, 끝나면 그 문서에 기록한다.
- `.claude/settings.json`으로 읽기를 막은 파일(샘플 PDF, 화면 캡처, 빌드 결과물)은 우회해서 읽지 않는다. PDF 구조는 pikepdf 스크립트로 본다.
- 다국어 작업(#34)에 대비해, 새 화면 문구는 한 곳에 모으고(`REPEAT_PASTE_TEXT` 방식), 화면 없는 계층에서는 한국어 문장 대신 오류 코드와 값을 넘기고, 조사를 붙이는 f-string(`을(를)` 등)을 새로 만들지 않는다.
