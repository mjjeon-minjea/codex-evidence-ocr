# OCR 출력 계약

## 원칙

`mean_confidence`는 OCR 엔진의 문자 인식 신호다. 규격 충족, 품질 합격, 문서 진위 또는 값의 정확성을 뜻하지 않는다.

## manifest.json

- `input.filename`: 사용자가 지정한 원본 파일명
- `input.sha256`: 원본 파일의 SHA-256
- `pages`: 페이지별 출력 요약
- `review_queue_count`: 검토 대상으로 분리된 페이지 수

## 페이지 분류

| 분류 | 의미 | 후속 행동 |
|---|---|---|
| `OCR_READY_FOR_REVIEW` | 인식 신호가 기준 이상 | 사람이 문맥·값·표 구조를 검토 |
| `OCR_REVIEW_REQUIRED` | 인식 신호가 낮음 | 원본 확대 또는 재처리 |
| `OCR_NO_TEXT` | 텍스트를 추출하지 못함 | 원본과 언어·해상도·영역 확인 |

## 검토 큐

`review_queue.csv`에는 자동 확정하지 않은 페이지와 사유만 기록한다. 이 파일은 수정·승인 기록이 아니라 후속 검토 목록이다.
