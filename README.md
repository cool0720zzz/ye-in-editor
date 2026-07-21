# 예인 가사 편집기

폰 브라우저에서 [ye-in-project](https://github.com/cool0720zzz/ye-in-project) 비공개 저장소의
가사·스타일 프롬프트를 편집하고 바로 커밋하는 단일 페이지 앱.

- 가사 블록과 스타일 프롬프트만 편집 — **설계 노트는 건드리지 않음**
- 코드펜스·줄바꿈(CRLF/LF)을 보존해 파일 구조가 깨지지 않음
- GitHub 토큰은 사용자 브라우저(localStorage)에만 저장. 이 저장소엔 어떤 비밀도 없음

`test_rebuild.mjs` — 블록 교체 로직 회귀 테스트 (`node test_rebuild.mjs <가사파일...>`)
