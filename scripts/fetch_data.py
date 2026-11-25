# -*- coding: utf-8 -*-
"""
우아숙소 수집기 — 한국관광공사 TourAPI 국문 관광정보 v2 (data.go.kr 15101578, apis.data.go.kr/B551011/KorService2)

1) areaBasedList2(contentTypeId=32, 숙박) 전체 목록(약 3천 건: 이름·주소·분류·좌표)을 받아 data/list.json.gz 에 저장.
2) 처음 보는 음식점만 detailIntro2(객실수·객실유형·체크인/아웃·환불규정·부대시설·주차·문의전화)를 받아 data/details/{id//2000}.json.gz 에 누적(숙소당 1호출).
   하루 호출 예산(기본 1000)만큼만 받고 멈춘다 — 내일 다시 돌리면 이어서 받는다. 최근 수정된 업소부터.
3) 목록에서 사라진 업소는 캐시에서도 제거. 응답이 JSON이 아니면(일일 한도 코드 22 → 저장 후 종료, 초당 제한 23 → 쉬고 재시도).
키: 환경변수 API_KEY → DATA_GO_KR_API_KEY → 로컬 ../hosppass/.env 의 API_KEY (코드에 넣지 않는다).
사용: python scripts/fetch_data.py [--budget N] [--list-only]
"""
import gzip, json, os, re, sys, time
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DET = DATA / "details"
DET.mkdir(parents=True, exist_ok=True)
BASE = "https://apis.data.go.kr/B551011/KorService2/"
GAP = 0.25
BUCKET = 2000
CALLS = 0
INTRO_KEYS = {"roomcount": "rc", "roomtype": "rt", "refundregulation": "rf", "checkintime": "ci", "checkouttime": "co", "chkcooking": "ck", "seminar": "sm", "sports": "sp",
              "sauna": "sa", "beauty": "be", "beverage": "bv", "karaoke": "ka", "barbecue": "bb", "campfire": "cf", "bicycle": "bi", "fitness": "fi", "publicpc": "pc",
              "publicbath": "pb", "subfacility": "sf", "foodplace": "fp", "reservationurl": "ru", "pickup": "pu", "parkinglodging": "pl", "infocenterlodging": "ic",
              "scalelodging": "sc", "accomcountlodging": "ac", "benikia": "bk", "goodstay": "gs", "hanok": "hk"}


class DailyLimit(Exception):
    pass


def api_key():
    for name in ("API_KEY", "DATA_GO_KR_API_KEY"):
        if os.environ.get(name):
            return os.environ[name].strip()
    for p in (ROOT / ".env", ROOT.parent / "hosppass" / ".env"):
        if p.exists():
            m = re.search(r"^API_KEY\s*=\s*(\S+)", p.read_text(encoding="utf-8"), re.M)
            if m:
                return m.group(1).strip("\"'")
    sys.exit("환경변수 API_KEY 가 필요합니다.")


KEY = api_key()
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"


def call(op, **params):
    """JSON body 반환. 일일 한도(코드 22)면 DailyLimit, 초당 제한(23)이면 쉬고 재시도."""
    global CALLS
    last = ""
    for attempt in range(8):
        try:
            CALLS += 1
            r = S.get(BASE + op, params=dict(serviceKey=KEY, MobileOS="ETC", MobileApp="wooasukso", _type="json", **params), timeout=90)
            txt = r.content.decode("utf-8", "replace")
            if "LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND" in txt or "<returnReasonCode>23<" in txt:
                last = "rate"
                time.sleep(15 + 5 * attempt)
                continue
            if "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS" in txt or "<returnReasonCode>22<" in txt:
                raise DailyLimit(txt[:200])
            j = json.loads(txt)
            h = j["response"]["header"]
            if h["resultCode"] != "0000":
                raise RuntimeError("%s %s" % (h["resultCode"], h["resultMsg"]))
            return j["response"]["body"]
        except (requests.RequestException, ValueError) as e:
            last = str(e)
            time.sleep(3 + 3 * attempt)
    raise RuntimeError("API 실패: %s %s" % (op, last))


def items(body):
    it = (body.get("items") or {})
    if not it:
        return []
    it = it.get("item") if isinstance(it, dict) else it
    return it if isinstance(it, list) else ([it] if it else [])


def pull(op, **params):
    out, page, n = [], 1, 1000
    while True:
        b = call(op, numOfRows=n, pageNo=page, **params)
        out += items(b)
        total = int(b.get("totalCount") or 0)
        if page * n >= total:
            return out
        page += 1
        time.sleep(GAP)


def bucket_of(cid):
    return int(cid) // BUCKET


def load_details():
    det = {}
    for p in DET.glob("*.json.gz"):
        det.update(json.loads(gzip.open(p, "rt", encoding="utf-8").read()))
    return det


def save_details(det):
    byb = {}
    for k, d in det.items():
        byb.setdefault(bucket_of(k), {})[k] = d
    keep = set()
    for b, its in byb.items():
        p = DET / ("%d.json.gz" % b)
        keep.add(p.name)
        blob = json.dumps(its, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        if p.exists() and gzip.decompress(p.read_bytes()) == blob:
            continue
        with gzip.GzipFile(p, "wb", compresslevel=9, mtime=0) as f:
            f.write(blob)
    for p in DET.glob("*.json.gz"):
        if p.name not in keep:
            p.unlink()


def fetch_one(cid):
    i = items(call("detailIntro2", contentId=cid, contentTypeId=32))
    if not i:
        return {}
    return {short: (i[0].get(long, "") or "").strip() for long, short in INTRO_KEYS.items() if (i[0].get(long, "") or "").strip()}


def main():
    budget = int(sys.argv[sys.argv.index("--budget") + 1]) if "--budget" in sys.argv else int(os.environ.get("DAILY_BUDGET", "1000"))
    lst = pull("areaBasedList2", contentTypeId=32, arrange="Q")
    print("숙박 목록", len(lst), flush=True)
    lp = DATA / "list.json.gz"
    if lp.exists():
        prev = len(json.loads(gzip.open(lp, "rt", encoding="utf-8").read()))
        if prev > 1000 and len(lst) < prev * 0.6:
            sys.exit("목록이 직전(%d)보다 크게 줄어(%d) 중단" % (prev, len(lst)))
    rows = [{"id": x["contentid"], "t": x.get("title", "").strip(), "a": (x.get("addr1", "") or "").strip(), "a2": (x.get("addr2", "") or "").strip(),
             "tel": (x.get("tel", "") or "").strip(), "c3": x.get("cat3", ""), "x": x.get("mapx", ""), "y": x.get("mapy", ""), "mod": x.get("modifiedtime", ""),
             "ac": x.get("areacode", ""), "sc": x.get("sigungucode", "")} for x in lst]
    with gzip.open(lp, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))
    if "--list-only" in sys.argv:
        return
    ids = {x["id"]: x for x in rows}
    det = load_details()
    n0 = len(det)
    det = {k: v for k, v in det.items() if k in ids}
    todo = [i for i in ids if i not in det]
    todo.sort(key=lambda i: -int(ids[i]["mod"] or 0))
    todo = todo[:max(0, budget - CALLS)]
    print("캐시 %d → 유지 %d, 이번에 받을 업소 %d개 (예산 %d)" % (n0, len(det), len(todo), budget), flush=True)
    done = fail = 0
    try:
        for n, cid in enumerate(todo, 1):
            try:
                det[cid] = fetch_one(cid)
                done += 1
            except DailyLimit:
                raise
            except Exception as e:
                fail += 1
                print("  실패", cid, str(e)[:80])
                if fail > 30:
                    print("실패 과다, 중단")
                    break
            if n % 200 == 0:
                save_details(det)
                print("  %d/%d 실패 %d" % (n, len(todo), fail), flush=True)
            time.sleep(GAP)
    except DailyLimit as e:
        print("일일 호출 한도 도달 — 저장하고 종료:", str(e)[:80].replace(chr(10), " "))
    save_details(det)
    print("완료: 목록 %d, 상세 보유 %d, 이번 신규 %d (실패 %d)" % (len(rows), len(det), done, fail))


if __name__ == "__main__":
    main()
