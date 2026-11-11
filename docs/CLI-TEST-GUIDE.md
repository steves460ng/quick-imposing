# CLI 직접 테스트 가이드

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-11 |
| 대상 | 명령행 도구를 직접 실행해 확인하는 사용자 |
| 기준 | `main` `2d84f9c` 이후. 명령은 Linux에서 실행해 결과를 확인함 |
| 관련 문서 | `README.md` (설치·명령 사용법), `docs/SPEC.md` v0.6, `docs/TASK-03-1.md`, `docs/TASK-03-2.md` |

대상 환경이 Windows이므로 PowerShell 기준으로 적었다. Windows 실행은 아직 검증되지 않았다. 이 가이드는 Windows 검증의 1차 점검으로도 쓴다(핸드오프 미결 6).

---

## 0. 준비

### 필요한 것

| 항목 | 내용 |
|---|---|
| Python | 3.12 이상. 설치할 때 "Add python.exe to PATH"를 켠다 |
| qpdf | GitHub 배포본의 Windows용 zip을 받아 `bin` 폴더를 PATH에 추가한다 |
| Poppler | Windows 빌드(예: GitHub `poppler-windows` 배포본)를 받아 `Library\bin` 폴더를 PATH에 추가한다. `pdftoppm`, `pdffonts`, `pdfimages`, `pdftotext`를 쓴다 |
| 글꼴 | 샘플 템플릿은 **Noto Sans CJK KR**을 쓴다. Windows 기본 글꼴이 아니므로 설치해야 한다 |

> Google Fonts의 "Noto Sans KR"은 이름이 다른 글꼴이라 찾지 못한다. "Noto Sans CJK KR"(noto-cjk 배포본)을 설치하거나, 글꼴 파일이 있는 폴더를 `--font-dir`로 지정한다.

### 설치 확인 (새 PowerShell 창)

```powershell
python --version
qpdf --version
pdftoppm -v
```

### 저장소 받기와 설치

```powershell
git clone https://github.com/steves460ng/quick-imposing
cd quick-imposing
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e '.[test]'
quick-imposing --help
```

- `Activate.ps1`이 실행 정책 때문에 막히면 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`를 먼저 실행한다.
- 이미 받은 저장소라면 `git pull`로 최신 main을 받는다.
- 이후 명령은 모두 `quick-imposing` 폴더에서, 가상환경을 켠 상태로 실행한다.
- 결과물은 `out\manual\` 아래에 만든다. `out\`은 저장소에 커밋하지 않는다.

## 1. 자동 테스트

```powershell
python -m pytest -q
python test03_runner.py
python test32_runner.py
```

| 명령 | 기대 결과 |
|---|---|
| pytest | 67 passed (Linux 기준) |
| `test03_runner.py` | 3-1차 10/10 PASS → `out\test03-1\summary.json` |
| `test32_runner.py` | 3-2차 11/11 PASS + 3-1차 회귀 → `out\test03-2\summary.json` |

같은 출력 폴더가 이미 있으면 거부된다. 다시 돌릴 때는 `--out out\test03-1-rerun`처럼 새 폴더를 지정한다.

## 2. 직접 실행 시나리오

### 2-1. 템플릿 만들기

수동 테스트용 템플릿 정의 `samples\manual\T31-front-3x8.json`을 쓴다. 3-1차 픽스처 `T31-front-3x8`의 템플릿 부분과 내용이 같고, 테스트 래퍼 없이 `create-template`에 바로 넣는 형식(`template@2`)이다.

| 항목 | 값 |
|---|---|
| 셀 | 85 × 50mm, 회전 −90° |
| 배열 | 3 × 8, 시작 (24, 49.5), 피치 86 × 51 |
| 채움 방향 | 정방향 |
| 텍스트 항목 | `product` (35, 14), `team` (100, 14), `date` (230, 14). Noto Sans CJK KR 9pt |

```powershell
quick-imposing create-template samples\manual\T31-front-3x8.json --base samples\input\base-front-blank.pdf --templates-root out\manual\templates
```

**확인할 것**
- `out\manual\templates\T31-front-3x8\`에 `template.json`과 `base.pdf`가 있다.
- `(Get-FileHash out\manual\templates\T31-front-3x8\base.pdf).Hash`가 `1AF4B47244303C60…`로 시작한다(원본과 같음).

템플릿 이름(`T31-front-3x8`)은 바꾸지 않는다. 2-2~2-5의 프로젝트가 이 이름으로 템플릿을 찾는다. `samples\manual\`의 파일은 직접 고치지 않는다(2-9 참조).

### 2-2. PDF 만들기 (24셀 + 텍스트)

```powershell
quick-imposing build samples\test03-1\projects\T31-01.qiproj.json --templates-root out\manual\templates --output out\manual\front-01.pdf
```

**확인할 것**
- 화면에 `"status": "PASS"`
- `front-01.pdf`, `.qiproj.json`, `.png`, `.report.json` 4개 파일이 생김
- PDF 상단에 `BC-COMBI`, `1팀`, `2026.11.11`이 보임
- **V15 방향**: 카드 위쪽이 판 오른쪽을 향함(−90°)
- **V18 Illustrator**: Illustrator로 열어 카드 24장이 모두 보임
- **글꼴**: Acrobat 문서 속성 → 글꼴에서 Noto Sans CJK KR이 "포함된 하위 집합"으로 표시됨

### 2-3. 덮어쓰기 거부

2-2 명령을 그대로 한 번 더 실행한다.

- `Refusing to overwrite: …front-01.pdf`가 나오고, 기존 파일 4개의 수정 시각이 바뀌지 않는다.

### 2-4. 템플릿에 없는 셀 (작업을 막는 유일한 경우)

```powershell
quick-imposing build samples\test03-1\projects\T31-07.qiproj.json --templates-root out\manual\templates --output out\manual\err-07.pdf
```

- 화면에 `"status": "FAIL"`, `CELL_NOT_IN_TEMPLATE`, `"cell": 25`
- PDF는 생기지 않고 `err-07.report.json`만 생긴다.

### 2-5. B 파일 없음 (빈칸으로 진행)

```powershell
quick-imposing build samples\test03-1\projects\T31-06.qiproj.json --templates-root out\manual\templates --output out\manual\miss-06.pdf
```

- PASS. PDF의 셀 2는 비어 있다.
- `miss-06.report.json`의 `info`에 `B_FILE_MISSING`(셀 2, `B-9.pdf`)이 기록된다.

### 2-6. 자동 배열 (역방향, 가운데 셀에서 시작)

```powershell
python -c "import json; d=json.load(open('samples/test03-2/template-defs/T32-rev-3x3.json',encoding='utf-8')); json.dump(d['template'],open('out/manual/rev.json','w',encoding='utf-8'),ensure_ascii=False,indent=2)"
quick-imposing create-template out\manual\rev.json --base samples\input\base-front-blank.pdf --templates-root out\manual\templates
quick-imposing autofill --template T32-rev-3x3 --templates-root out\manual\templates --start-cell 5 --files samples\test03-2\data\c-10.pdf samples\test03-2\data\c-3.pdf samples\test03-2\data\c-11.pdf samples\test03-2\data\c-1.pdf samples\test03-2\data\c-2.pdf --output out\manual\af\rev5.qiproj.json
```

`rev5.qiproj.json`을 메모장으로 열어 배정을 확인한다. 파일은 일부러 섞인 순서로 넣었다.

| 셀 | 파일 | order |
|---|---|---|
| 5 | c-1 | 1 |
| 4 | c-2 | 2 |
| 9 | c-3 | 3 |
| 8 | c-10 | 4 |
| 7 | c-11 | 5 |

- 셀 6은 비어 있다.
- `c-10`이 `c-2`보다 앞에 오면 숫자 정렬 실패다.

### 2-7. 자동 배열 막힘

```powershell
quick-imposing autofill --template T32-rev-3x3 --templates-root out\manual\templates --start-cell 8 --files samples\test03-2\data\c-1.pdf samples\test03-2\data\c-2.pdf samples\test03-2\data\c-3.pdf --output out\manual\af\block.qiproj.json
```

- 셀 8에 c-1, 셀 7에 c-2가 들어간다.
- 경고 `AUTOFILL_BLOCKED`(`end_of_cells`)와 미배정 파일 `c-3.pdf`
- 리포트 파일 이름은 `block.qiproj.autofill.json`이다.

### 2-8. 자동 배열 결과로 PDF 만들기

```powershell
quick-imposing build out\manual\af\rev5.qiproj.json --templates-root out\manual\templates --output out\manual\af\pdf\rev5.pdf
```

- PASS. 프로젝트와 다른 폴더에 저장해도 B 경로가 새 위치 기준으로 다시 계산되는지 확인한다.

### 2-9. Windows 기본 글꼴 (선택, 권장)

Windows 시스템 글꼴 폴더 검색은 아직 확인한 적이 없다. 저장소의 템플릿을 복사한 뒤 사본만 고친다.

```powershell
Copy-Item samples\manual\T31-front-3x8.json out\manual\malgun.json
notepad out\manual\malgun.json
```

메모장에서 `"Noto Sans CJK KR"` 3곳을 `"Malgun Gothic"`으로 바꿔 저장한다. 템플릿 폴더는 2-1과 다르게 지정한다.

```powershell
quick-imposing create-template out\manual\malgun.json --base samples\input\base-front-blank.pdf --templates-root out\manual\templates-malgun
quick-imposing build samples\test03-1\projects\T31-01.qiproj.json --templates-root out\manual\templates-malgun --output out\manual\malgun-01.pdf
```

- PASS가 나오고 한글이 맑은 고딕으로 보이면 통과다.
- `FONT_NOT_FOUND`나 임베드 권한 오류가 나면 그 메시지가 확인 결과다.

## 3. 결과 기록

다음을 남긴다.

- Windows 버전, 0단계 각 도구의 버전
- 1단계 세 명령의 마지막 줄 (통과 수)
- 2단계에서 기대와 다른 항목: 명령, 화면 출력, 해당 `.report.json`
- V15·V18·글꼴을 눈으로 확인한 결과
