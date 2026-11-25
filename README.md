# 우아숙소 (wooasukso)

한국관광공사 TourAPI 국문 관광정보 v2(`B551011/KorService2`, 콘텐츠 유형 32=숙박, 약 3.1천 곳)로 만든 숙소 정보 사이트(Python 정적 생성기). https://wooasukso.wooahouse.com — 우아숙박(wooastay, LOCALDATA 31만 곳 허브)과 별개의 **체크인·환불규정 상세** 사이트.

- `scripts/fetch_data.py` — `areaBasedList2`로 목록, `detailIntro2`(객실수·객실유형·체크인/아웃·환불규정·부대시설·주차·문의 전화)로 숙소당 1호출 상세를 `data/details/{id//2000}.json.gz`에 누적. 하루 예산 기본 1000호출(TourAPI 일일 한도 ~3,300을 여행코스·우아메뉴와 공유: 05:00 코스, 05:30 메뉴 2000, 05:45 숙소 1000).
- 유형(펜션·호텔·한옥 등)은 상호 키워드 정규식(cat3는 대부분 비어 있음), 지역은 addr1 파싱. 체크인·객실·환불규정이 모두 비면 페이지 미생성, 이미지·개요 미사용.
- `scripts/build_site.py` — 숙소 상세 `/place/{id}/`, 지역·시군구·유형·편의시설(바비큐·취사·사우나 등) 허브, 검색 인덱스. 상세가 30곳 미만이면 noindex '준비 중' 홈만 배포(네이버 태그 포함).
- Actions: push 시 빌드, 매일 KST 05:45 수집→커밋→빌드. 시크릿 `API_KEY`. 네이버 토큰은 `scripts/common.py` `NAVER_TOKEN`.
