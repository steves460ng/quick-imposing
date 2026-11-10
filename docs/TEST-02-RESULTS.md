# 2차 테스트 결과

- 기준: `docs/TEST-02.md` v0.1, `docs/SPEC.md` v0.4
- 기준 커밋: `bcba49f` (윤곽선 처리된 2차 샘플)
- 실행일: 2026-11-10
- Python 3.12.14, pikepdf 10.18.0 (libqpdf 12.4.2), qpdf CLI 12.2.0, Poppler 25.03.0

## 실행 결과

`python test02_runner.py`로 7개 템플릿을 실행하고 `samples/expected/`와 독립 대조했다. **자동 검사 7/7 PASS**. 원본 PDF·템플릿·기대값 파일의 실행 전후 SHA-256은 동일하다.

| 케이스 | 결과 | 확인 사항 |
|---|---|---|
| T2-01 | PASS | 24개 배치, 기대 행렬·BBox·좌표 일치 |
| T2-02 | PASS | 7개 배치, 8번 슬롯 비어 있음, 맞닿는 경계와 0.5mm 간격 |
| T2-03 | PASS | SLOT_OVERLAP, PDF 없음 |
| T2-04 | PASS | SLOT_OUT_OF_SAFE_AREA, PDF 없음 |
| T2-05 | PASS | FILE_NOT_FOUND, PDF 없음 |
| T2-06 | PASS | UNKNOWN_SLOT, PDF 없음 |
| T2-07 | PASS | DUPLICATE_SLOT_ASSIGNMENT, PDF 없음 |

정상 케이스에서 V1~V14·V16, 원본 스트림 대응(C2), 빈 슬롯 픽셀 일치(C3), 베이스 폰트 2개만 존재(C4), 카드 텍스트 연산자 없음(C5), 실제 BBox 변환 경계(C6), 두 번 실행한 페이지 콘텐츠·리소스 동일(C7)을 확인했다. **V15는 사람의 방향 확인이 필요한 항목으로 미완료 상태다. 자동 PASS가 V15 완료를 의미하지 않는다.**

전체 회귀 테스트: `python -m pytest -q` — **32 passed**. 기존 프리셋·입력 보존·Illustrator 처리 외에 네 가지 회전의 실제 PDF 생성, 잘못된 스키마, 복수 오류 수집, 크기 부족·다중 페이지·잘못된 PDF, TrimBox 대체 경고, 배정 순서 변경을 포함한다.

## 산출물과 재실행

- `out/test02/summary.json`: 전체 요약
- `out/test02/<template>/report.json`: 각 케이스 리포트
- 정상 2개 폴더: `result.pdf`, `preview.png`
- 오류 5개 폴더: 리포트만 존재

`out/`은 커밋하지 않는다. PR 체크아웃에서 의존성을 설치한 뒤 `python test02_runner.py`로 재생성할 수 있다. 기존 출력이 있으면 `--out out/test02-rerun`처럼 새 경로를 지정한다.

## Illustrator 이슈 처리

1차 결과가 Chrome·macOS PDF 미리보기에는 보이나 Illustrator에서 B 카드가 보이지 않는 현상이 보고됐다. 베이스와 결과에 `/PieceInfo/Illustrator/Private/AIPDFPrivateData1` 등 카드 배치 전의 전용 편집 데이터가 남아 있음을 확인했다. Illustrator가 이 데이터로 문서를 다시 열 가능성이 원인 후보였다.

결과 저장 전에 문서·페이지의 `/PieceInfo/Illustrator`만 제거한다. 비어 버린 PieceInfo는 삭제하고 다른 프로그램의 PieceInfo는 유지한다. 처리 위치는 `illustrator_private_data_removed`에 기록한다. 원본 입력과 PDF 콘텐츠·폰트·이미지·레이어는 보존한다. 1차 수정 전후 콘텐츠 스트림·리소스·미리보기 픽셀 동일성을 확인했고, 제거·타 앱 데이터 보존·반복 적용 및 저장 후 검사 회귀 테스트를 추가했다.

2차 생성 결과에도 같은 처리를 적용했으며 구조·스트림·렌더링 검사는 통과했다. **Illustrator에서 직접 재개봉한 결과는 검증하지 못했다.** 전용 편집 데이터 제거로 Illustrator 고유 편집 구조의 왕복 보존은 지원하지 않는다.
