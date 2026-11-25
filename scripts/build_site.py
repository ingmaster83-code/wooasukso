# -*- coding: utf-8 -*-
"""우아숙소 정적 사이트 생성기.
입력: data/list.json.gz(숙박 목록: 이름·주소·좌표) · data/details/*.json.gz(객실수·체크인·환불규정·부대시설 등)
출력: _site/  (숙소 상세, 지역·유형·편의시설 허브, 안내, 검색 인덱스, sitemap)
상세가 아직 없는 숙소는 만들지 않는다(상세는 매일 예산만큼 쌓임). 이미지는 쓰지 않는다(KTO 이미지 라이선스).
"""
import collections, gzip, html as ihtml, json, os, re, shutil, sys
from datetime import datetime, timedelta, timezone

from common import *  # noqa

sys.stdout.reconfigure(encoding="utf-8")
DATA = pathlib.Path(os.environ["DATA_DIR"]) if os.environ.get("DATA_DIR") else ROOT / "data"
TODAY = (datetime.now(timezone.utc) + timedelta(hours=9)).date()

SHORT = {"서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
         "경기도": "경기", "강원특별자치도": "강원", "강원도": "강원", "충청북도": "충북", "충청남도": "충남", "전북특별자치도": "전북", "전라북도": "전북", "전라남도": "전남",
         "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주", "전남광주통합특별시": "전남광주"}

# 상호 키워드로 숙소 유형 분류 (앞에서부터 먼저 맞는 유형)
TYPES = [("한옥", r"한옥|고택|전통가옥"), ("풀빌라", r"풀빌라|풀 빌라|프라이빗"), ("글램핑·캠핑", r"글램핑|카라반|캠핑|오토캠"), ("게스트하우스", r"게스트하우스|게스트 하우스|호스텔|hostel|게하"),
         ("리조트·콘도", r"리조트|콘도|resort|오션뷰 호텔앤리조트"), ("모텔", r"모텔|motel"), ("민박·농가", r"민박|농가|농촌|홈스테이|독채"), ("호텔", r"호텔|hotel|레지던스|관광호텔"), ("펜션", r"펜션|pension|별장|스테이|stay")]
TRE = [(n, re.compile(r, re.I)) for n, r in TYPES]
C3 = {"B02011600": "한옥", "B02011100": "게스트하우스", "B02010700": "펜션", "B02010100": "호텔", "B02011200": "민박·농가", "B02010900": "모텔", "B02011000": "민박·농가",
      "B02010500": "리조트·콘도", "B02010600": "게스트하우스", "B02011300": "호텔"}
FEATS = [("bb", "바비큐"), ("ck", "객실 내 취사"), ("sa", "사우나"), ("pb", "공동 목욕탕"), ("ka", "노래방"), ("sm", "세미나실"), ("cf", "캠프파이어"), ("fi", "피트니스"), ("bi", "자전거 대여"), ("sp", "스포츠 시설"), ("pc", "공용 PC")]
FNAME = dict(FEATS)
FSLUG = {"bb": "바비큐", "ck": "객실취사", "sa": "사우나", "pb": "공동목욕탕", "ka": "노래방", "sm": "세미나실", "cf": "캠프파이어", "fi": "피트니스", "bi": "자전거대여", "sp": "스포츠시설", "pc": "공용PC"}


def un(s):
    return ihtml.unescape(ihtml.unescape(s or ""))


def plain(s):
    s = un(s)
    s = re.sub(r"<br\s*/?>|</p>|\\n", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"[ \t ]+", " ", s.replace("\r", ""))
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def one(s):
    return re.sub(r"\s+", " ", plain(s)).strip()


def cut(s, n):
    return s if len(s) <= n else s[:n].rstrip(" ,/·") + "…"


def flag(v):
    v = (v or "").strip()
    return v not in ("", "0", "불가능", "없음", "불가", "N")


def classify(name, c3):
    for t, r in TRE:
        if r.search(name):
            return t
    return C3.get(c3, "")


def region_of(addr):
    t = (addr or "").split()
    if not t:
        return "", ""
    sido = SHORT.get(t[0], "")
    if not sido:
        return "", ""
    if sido == "세종":
        return sido, "세종시"
    return sido, (t[1] if len(t) > 1 and re.search(r"(시|군|구)$", t[1]) else "")


def load():
    rows = json.loads(gzip.open(DATA / "list.json.gz", "rt", encoding="utf-8").read())
    det = {}
    for p in (DATA / "details").glob("*.json.gz"):
        det.update(json.loads(gzip.open(p, "rt", encoding="utf-8").read()))
    ps = []
    for r in rows:
        d = det.get(r["id"])
        if not d:
            continue
        name = un(r["t"]).strip()
        ci, co, rc = one(d.get("ci")), one(d.get("co")), one(d.get("rc"))
        rf = one(d.get("rf"))
        if not name or not (ci or rc or rf):
            continue
        sido, sgg = region_of(r["a"])
        if not sido:
            continue
        feats = [k for k, _ in FEATS if flag(d.get(k))]
        ps.append(dict(id=r["id"], name=name, addr=(r["a"] + (" " + r["a2"] if r["a2"] else "")).strip(), sido=sido, sgg=sgg, x=r["x"], y=r["y"], mod=r["mod"], typ=classify(name, r["c3"]),
                       rc=rc, rt=one(d.get("rt")), ci=ci, co=co, rf=rf, ck=one(d.get("ck")), sf=one(d.get("sf")), fp=one(d.get("fp")), pl=one(d.get("pl")), pu=one(d.get("pu")), ic=one(d.get("ic")),
                       ru=(d.get("ru") or "").strip(), feats=feats))
    return ps, len(rows)


def plink(p):
    return '<a href="/place/%s/">%s</a>' % (p["id"], esc(p["name"]))


def ptable(L, cap=150, region=True):
    L = L[:cap]
    head = "<tr><th>숙소</th>%s<th>유형</th><th>객실</th><th>체크인·아웃</th></tr>" % ("<th>지역</th>" if region else "")
    rows = []
    for p in L:
        io = (p["ci"] or "-") + (" / " + p["co"] if p["co"] else "")
        rows.append("<tr><td>%s</td>%s<td>%s</td><td>%s</td><td>%s</td></tr>" % (plink(p), ("<td>%s</td>" % esc((p["sido"] + " " + p["sgg"]).strip())) if region else "", esc(p["typ"] or "-"), esc((p["rc"] + "실") if p["rc"] else "-"), esc(cut(io, 24))))
    return '<div class="tbl-wrap"><table class="tbl">%s%s</table></div>' % (head, "".join(rows))


def stat(L):
    tc = collections.Counter(p["typ"] for p in L if p["typ"])
    s = "체크인 시간·객실 정보가 등록된 숙소 <b>%d곳</b>입니다." % len(L)
    if tc:
        s += " " + ", ".join("%s %d곳" % (k, v) for k, v in tc.most_common(4)) + " 순으로 많습니다."
    return '<p class="lead">%s</p>' % s


def hub(path, h1, sub, L, extra="", cap=150, title=None, desc=None, crumbs=None, prio="0.7", region=True, faq=None):
    body = ['<div class="page-head"><h1>%s</h1><p>%s</p></div>' % (esc(h1), esc(sub)), stat(L), ad(), extra, '<h2 class="group-title">숙소 목록</h2>', ptable(L, cap, region)]
    if len(L) > cap:
        body.append('<p class="note">숙소가 많아 %d곳만 표시했습니다. 지역·유형별 페이지에서 좁혀 보세요.</p>' % cap)
    write(path, layout(path, title or h1, desc or sub, "\n".join(b for b in body if b), faq, crumbs or [("홈", "/")], coupang=True), prio)


def page_place(p, by_sgg, hubs_ok):
    region = (p["sido"] + " " + p["sgg"]).strip()
    kind = p["typ"] or "숙소"
    lead = ["<b>%s</b>은(는) %s에 있는 %s입니다." % (esc(p["name"]), esc(region), esc(kind))]
    if p["rc"]:
        lead.append("객실은 %s실이고," % esc(p["rc"]))
    if p["ci"]:
        lead.append("체크인은 %s%s입니다." % (esc(p["ci"]), (", 체크아웃은 %s" % esc(p["co"])) if p["co"] else ""))
    feats = [FNAME[k] for k in p["feats"]]
    rows = [("숙소 유형", p["typ"]), ("객실 수", (p["rc"] + "실") if p["rc"] else ""), ("객실 유형", p["rt"]), ("체크인", p["ci"]), ("체크아웃", p["co"]), ("객실 내 취사", p["ck"]),
            ("편의시설", ", ".join(feats)), ("기타 부대시설", p["sf"]), ("식음료장", p["fp"]), ("주차", p["pl"]), ("픽업", p["pu"]), ("문의 전화", p["ic"]), ("주소", p["addr"])]
    tbl = '<div class="tbl-wrap"><table class="tbl">%s</table></div>' % "".join("<tr><th>%s</th><td>%s</td></tr>" % (a, esc(b)) for a, b in rows if b)
    body = ['<div class="page-head"><h1>%s</h1><p>%s</p></div>' % (esc(p["name"]), esc(" · ".join(x for x in (region, p["typ"]) if x))), '<p class="lead">%s</p>' % " ".join(lead), ad(), tbl]
    if p["rf"]:
        body.append('<h2 class="group-title">취소·환불 규정</h2><div class="lead">%s</div>' % esc(cut(p["rf"], 700)))
    acts = []
    if p["x"] and p["y"]:
        acts.append('<a class="btn" href="https://map.kakao.com/link/map/%s,%s,%s">🗺️ 지도에서 위치 보기</a>' % (urllib.parse.quote(p["name"][:40]), p["y"], p["x"]))
    if p["ru"].startswith("http"):
        acts.append('<a class="btn" href="%s" rel="nofollow noopener" target="_blank">📅 예약 페이지</a>' % esc(p["ru"]))
    if acts:
        body.append("<p>%s</p>" % " ".join(acts))
    body.append('<div class="note-box">숙소 정보는 한국관광공사 TourAPI(공공데이터포털) 기준이며, 체크인 시간·환불 규정·객실·요금은 바뀔 수 있습니다. 예약 전에 숙소에 확인하세요.</div>')
    sib = [o for o in by_sgg.get((p["sido"], p["sgg"]), []) if o is not p and (not p["typ"] or o["typ"] == p["typ"])][:8]
    if len(sib) < 8:
        sib += [o for o in by_sgg.get((p["sido"], p["sgg"]), []) if o is not p and o not in sib][:8 - len(sib)]
    if sib:
        body.append('<h2 class="group-title">같은 지역 다른 숙소 <small>%s</small></h2>' % esc(region))
        body.append(ptable(sib, 8, False))
    chips = []
    if ("region", p["sido"]) in hubs_ok:
        chips.append('<a class="chip" href="/region/%s/">%s 숙소</a>' % (q(p["sido"]), esc(p["sido"])))
    if p["sgg"] and ("sgg", p["sido"], p["sgg"]) in hubs_ok:
        chips.append('<a class="chip" href="/region/%s/%s/">%s %s 숙소</a>' % (q(p["sido"]), q(p["sgg"]), esc(p["sido"]), esc(p["sgg"])))
    if p["typ"] and ("ts", p["typ"], p["sido"]) in hubs_ok:
        chips.append('<a class="chip" href="/type/%s/%s/">%s %s</a>' % (q(p["typ"]), q(p["sido"]), esc(p["sido"]), esc(p["typ"])))
    for k in p["feats"][:3]:
        if ("fs", k, p["sido"]) in hubs_ok:
            chips.append('<a class="chip" href="/feature/%s/%s/">%s %s 가능</a>' % (q(FSLUG[k]), q(p["sido"]), esc(p["sido"]), esc(FNAME[k])))
    if chips:
        body.append('<div class="chips">%s</div>' % "".join(chips))
    faq = []
    if p["ci"]:
        faq.append(("%s의 체크인·체크아웃 시간은 언제인가요?" % p["name"], "공공데이터에는 체크인이 %s%s로 등록돼 있습니다. 성수기·객실에 따라 달라질 수 있어 예약 전에 확인하세요." % (p["ci"], (", 체크아웃이 %s" % p["co"]) if p["co"] else "")))
    if p["rf"]:
        faq.append(("%s의 취소·환불 규정은 어떻게 되나요?" % p["name"], "등록된 규정은 다음과 같습니다. %s" % cut(p["rf"], 300)))
    if p["rc"]:
        faq.append(("%s에는 객실이 몇 개 있나요?" % p["name"], "객실은 %s실로 등록돼 있습니다.%s" % (p["rc"], (" 객실 유형은 %s입니다." % p["rt"]) if p["rt"] else "")))
    if feats:
        faq.append(("%s에서 이용할 수 있는 편의시설은 무엇인가요?" % p["name"], "%s 등이 등록돼 있습니다." % ", ".join(feats[:6])))
    crumbs = [("홈", "/"), (p["sido"], "/region/%s/" % p["sido"]), ((p["name"][:26] + "…") if len(p["name"]) > 26 else p["name"], "/place/%s/" % p["id"])]
    ld = [{"@context": "https://schema.org", "@type": "LodgingBusiness", "name": p["name"], "address": p["addr"]}]
    if p["ci"]:
        ld[0]["checkinTime"] = p["ci"][:40]
    if p["co"]:
        ld[0]["checkoutTime"] = p["co"][:40]
    if p["x"] and p["y"]:
        ld[0]["geo"] = {"@type": "GeoCoordinates", "latitude": p["y"], "longitude": p["x"]}
    title = "%s 체크인·객실·환불규정 - %s %s" % (p["name"], region, kind)
    desc = "%s(%s %s) %s%s%s." % (p["name"], region, kind, ("객실 %s실, " % p["rc"]) if p["rc"] else "", ("체크인 %s" % cut(p["ci"], 20)) if p["ci"] else "", (", 체크아웃 %s" % cut(p["co"], 20)) if p["co"] else "")
    write("/place/%s/" % p["id"], layout("/place/%s/" % p["id"], title, desc, "\n".join(body), faq or None, crumbs, "article", ld, coupang=True), "0.6")


def build():
    ps, total_rows = load()
    print("숙소", len(ps), "/ 목록", total_rows)
    if len(ps) < 30:
        # 초기 수집 중에는 '준비 중' 홈만 배포(noindex) — 네이버 소유확인 태그는 포함
        OUT.mkdir(parents=True, exist_ok=True)
        for ch in OUT.iterdir():
            shutil.rmtree(ch) if ch.is_dir() else ch.unlink()
        write("/", layout("/", "숙소 정보 수집 중 | 우아숙소", "한국관광공사 숙박 정보를 수집하고 있습니다.", '<div class="page-head"><h1>우아숙소 — 준비 중</h1><p>한국관광공사 숙박 정보를 매일 조금씩 수집하고 있어요. 곧 체크인·객실·환불규정으로 숙소를 찾을 수 있습니다.</p></div>', None, None, noindex=True), sitemap=False)
        finish()
        return
    ps.sort(key=lambda p: (-int(p["mod"] or 0), p["id"]))
    by_sido, by_sgg, by_t, by_ts, by_f, by_fs = (collections.defaultdict(list) for _ in range(6))
    for p in ps:
        by_sido[p["sido"]].append(p)
        if p["sgg"]:
            by_sgg[(p["sido"], p["sgg"])].append(p)
        if p["typ"]:
            by_t[p["typ"]].append(p)
            by_ts[(p["typ"], p["sido"])].append(p)
        for k in p["feats"]:
            by_f[k].append(p)
            by_fs[(k, p["sido"])].append(p)
    hubs_ok = {("region", s) for s in by_sido} | {("sgg", s, g) for (s, g), L in by_sgg.items() if len(L) >= 3} | {("type", t) for t, L in by_t.items() if len(L) >= 5} \
        | {("ts", t, s) for (t, s), L in by_ts.items() if len(L) >= 3 and len(by_t[t]) >= 5} | {("feat", k) for k, L in by_f.items() if len(L) >= 5} | {("fs", k, s) for (k, s), L in by_fs.items() if len(L) >= 3 and len(by_f[k]) >= 5}
    OUT.mkdir(parents=True, exist_ok=True)
    for ch in OUT.iterdir():
        shutil.rmtree(ch) if ch.is_dir() else ch.unlink()
    for p in ps:
        page_place(p, by_sgg, hubs_ok)
    # 지역
    for s, L in by_sido.items():
        gc = collections.Counter(p["sgg"] for p in L if p["sgg"])
        tc = collections.Counter(p["typ"] for p in L if p["typ"])
        extra = ""
        if tc:
            extra += '<h2 class="group-title">유형별</h2><div class="chips">%s</div>' % "".join(
                ('<a class="chip" href="/type/%s/%s/">%s <small>%d</small></a>' % (q(t), q(s), esc(t), n)) if ("ts", t, s) in hubs_ok else '<span class="chip">%s <small>%d</small></span>' % (esc(t), n) for t, n in tc.most_common())
        if gc:
            extra += '<h2 class="group-title">시군구별</h2><div class="chips">%s</div>' % "".join(
                ('<a class="chip" href="/region/%s/%s/">%s <small>%d</small></a>' % (q(s), q(g), esc(g), n)) if n >= 3 else '<span class="chip">%s <small>%d</small></span>' % (esc(g), n) for g, n in gc.most_common(80))
        hub("/region/%s/" % s, "%s 숙소 %d곳 - 체크인·객실·환불규정" % (s, len(L)), "지역 숙소의 체크인 시간과 객실 정보", L, extra, 150, "%s 숙소 %d곳 - 체크인 시간·환불 규정" % (s, len(L)),
            "%s 펜션·호텔·한옥 등 숙소 %d곳의 체크인·체크아웃, 객실 수, 환불 규정, 편의시설을 정리했습니다." % (s, len(L)), [("홈", "/"), ("지역별", "/region/"), (s, "/region/%s/" % s)], "0.8",
            faq=[("%s 숙소는 몇 곳이 등록돼 있나요?" % s, "한국관광공사 공공데이터에 체크인·객실 정보가 등록된 숙소 기준 %d곳입니다." % len(L))])
    for (s, g), L in by_sgg.items():
        if len(L) >= 3:
            hub("/region/%s/%s/" % (s, g), "%s %s 숙소 %d곳" % (s, g, len(L)), "체크인·객실·환불규정", L, "", 150, "%s %s 숙소 %d곳 - 체크인·환불 규정" % (s, g, len(L)),
                "%s %s의 숙소 %d곳의 체크인 시간과 객실, 환불 규정을 정리했습니다." % (s, g, len(L)), [("홈", "/"), (s, "/region/%s/" % s), (g, "/region/%s/%s/" % (s, g))], "0.6", region=False)
    cards = "".join('<a class="card" href="/region/%s/"><b>%s</b><span>%d곳</span></a>' % (q(s), esc(s), len(L)) for s, L in sorted(by_sido.items(), key=lambda t: -len(t[1])))
    write("/region/", layout("/region/", "지역별 숙소", "시도별 펜션·호텔·한옥 숙소의 체크인 시간과 환불 규정을 확인하세요.", '<div class="page-head"><h1>지역별 숙소</h1></div>' + ad() + '<div class="card-grid">%s</div>' % cards, None, [("홈", "/"), ("지역별", "/region/")]), "0.8")
    # 유형
    for t, L in by_t.items():
        if len(L) < 5:
            continue
        sc = collections.Counter(p["sido"] for p in L)
        extra = '<h2 class="group-title">지역별</h2><div class="chips">%s</div>' % "".join(
            ('<a class="chip" href="/type/%s/%s/">%s <small>%d</small></a>' % (q(t), q(s), esc(s), n)) if n >= 3 else '<span class="chip">%s <small>%d</small></span>' % (esc(s), n) for s, n in sc.most_common())
        hub("/type/%s/" % t, "%s %d곳 - 지역별 체크인·환불규정" % (t, len(L)), "%s 숙소 목록" % t, L, extra, 150, "%s 추천 지역별 %d곳 - 체크인·객실·환불규정" % (t, len(L)),
            "%s %d곳을 지역별로 정리했습니다. 체크인 시간, 객실 수, 환불 규정, 편의시설을 확인하세요." % (t, len(L)), [("홈", "/"), ("유형별", "/type/"), (t, "/type/%s/" % t)], "0.8")
        for s, n in sc.items():
            if n >= 3:
                L2 = by_ts[(t, s)]
                hub("/type/%s/%s/" % (t, s), "%s %s %d곳" % (s, t, len(L2)), "체크인·객실·환불규정", L2, "", 150, "%s %s %d곳 - 체크인·환불 규정" % (s, t, len(L2)),
                    "%s의 %s %d곳의 체크인 시간과 객실 정보, 환불 규정을 정리했습니다." % (s, t, len(L2)), [("홈", "/"), (t, "/type/%s/" % t), (s, "/type/%s/%s/" % (t, s))], "0.6", region=False)
    cards = "".join('<a class="card" href="/type/%s/"><b>%s</b><span>%d곳</span></a>' % (q(t), esc(t), len(L)) for t, L in sorted(by_t.items(), key=lambda x: -len(x[1])) if len(L) >= 5)
    write("/type/", layout("/type/", "유형별 숙소", "펜션·호텔·한옥·게스트하우스 등 숙소 유형별로 찾으세요.", '<div class="page-head"><h1>유형별 숙소</h1></div>' + ad() + '<div class="card-grid">%s</div>' % cards, None, [("홈", "/"), ("유형별", "/type/")]), "0.8")
    # 편의시설
    for k, L in by_f.items():
        if len(L) < 5:
            continue
        nm = FNAME[k]
        sc = collections.Counter(p["sido"] for p in L)
        extra = '<h2 class="group-title">지역별</h2><div class="chips">%s</div>' % "".join(
            ('<a class="chip" href="/feature/%s/%s/">%s <small>%d</small></a>' % (q(FSLUG[k]), q(s), esc(s), n)) if n >= 3 else '<span class="chip">%s <small>%d</small></span>' % (esc(s), n) for s, n in sc.most_common())
        hub("/feature/%s/" % FSLUG[k], "%s 가능한 숙소 %d곳" % (nm, len(L)), "%s이(가) 등록된 숙소" % nm, L, extra, 150, "%s 가능한 숙소 %d곳 - 지역별" % (nm, len(L)),
            "%s이(가) 가능한 숙소 %d곳을 지역별로 정리했습니다. 체크인 시간과 객실, 환불 규정도 확인하세요." % (nm, len(L)), [("홈", "/"), ("편의시설별", "/feature/"), (nm, "/feature/%s/" % FSLUG[k])], "0.8")
        for s, n in sc.items():
            if n >= 3:
                L2 = by_fs[(k, s)]
                hub("/feature/%s/%s/" % (FSLUG[k], s), "%s %s 가능한 숙소 %d곳" % (s, nm, len(L2)), "체크인·객실·환불규정", L2, "", 150, "%s %s 가능 숙소 %d곳" % (s, nm, len(L2)),
                    "%s에서 %s이(가) 가능한 숙소 %d곳을 정리했습니다." % (s, nm, len(L2)), [("홈", "/"), (nm, "/feature/%s/" % FSLUG[k]), (s, "/feature/%s/%s/" % (FSLUG[k], s))], "0.6", region=False)
    cards = "".join('<a class="card" href="/feature/%s/"><b>%s</b><span>%d곳</span></a>' % (q(FSLUG[k]), esc(FNAME[k]), len(L)) for k, L in sorted(by_f.items(), key=lambda x: -len(x[1])) if len(L) >= 5)
    write("/feature/", layout("/feature/", "편의시설별 숙소", "바비큐·객실 취사·사우나·노래방 등 편의시설별로 숙소를 찾으세요.", '<div class="page-head"><h1>편의시설별 숙소</h1></div>' + ad() + '<div class="card-grid">%s</div>' % cards, None, [("홈", "/"), ("편의시설별", "/feature/")]), "0.8")
    # 홈
    tcards = "".join('<a class="card" href="/type/%s/"><b>%s</b><span>%d곳</span></a>' % (q(t), esc(t), len(L)) for t, L in sorted(by_t.items(), key=lambda x: -len(x[1])) if len(L) >= 5)
    body = ['<div class="hero"><h1>체크인·환불규정으로 찾는 숙소</h1><p>한국관광공사 공공데이터의 숙소 %s곳을 객실·체크인·환불규정·편의시설로 찾으세요</p>'
            '<div class="today-box"><div><small>등록 숙소</small><b>%s곳</b></div><div><small>숙소 유형</small><b>%d개</b></div><div><small>시군구</small><b>%d곳</b></div></div></div>' % (
                "{:,}".format(len(ps)), "{:,}".format(len(ps)), sum(1 for L in by_t.values() if len(L) >= 5), len(by_sgg)),
            '<div class="search-box"><input id="q" type="search" placeholder="숙소 검색 (예: 가평 펜션, 전주 한옥)" autocomplete="off"><div id="sr" class="sr-list"></div></div>', ad(),
            '<h2 class="group-title">유형별</h2><div class="card-grid">%s</div>' % tcards,
            '<h2 class="group-title">지역별</h2><div class="card-grid">%s</div>' % "".join('<a class="card" href="/region/%s/"><b>%s</b><span>%d곳</span></a>' % (q(s), esc(s), len(L)) for s, L in sorted(by_sido.items(), key=lambda t: -len(t[1]))),
            '<h2 class="group-title">최근 갱신된 숙소</h2>', ptable(ps[:10], 10), '<script src="/assets/js/search.js"></script>']
    faq = [("숙소 정보는 어디서 가져왔나요?", "한국관광공사가 공공데이터포털에 공개한 TourAPI 숙박 정보를 정리했습니다. 객실 수, 체크인·체크아웃, 환불 규정은 사업자가 등록한 값입니다."),
           ("예약도 할 수 있나요?", "이 사이트는 예약을 대행하지 않고 정보만 정리합니다. 예약 링크가 등록된 숙소는 해당 숙소의 예약 페이지로 연결됩니다."),
           ("전국 모든 숙소가 있나요?", "공공데이터에 숙박 정보로 등록된 곳만 싣습니다. 일반 숙박업소 전체 현황은 우아숙박에서 볼 수 있습니다.")]
    ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": "우아숙소", "url": BASE + "/", "potentialAction": {"@type": "SearchAction", "target": BASE + "/?q={q}", "query-input": "required name=q"}}]
    write("/", layout("/", "체크인·환불규정으로 찾는 숙소 %s곳 | 우아숙소" % "{:,}".format(len(ps)), "한국관광공사 공공데이터의 펜션·호텔·한옥 %s곳을 객실·체크인·환불규정·편의시설로 찾으세요." % "{:,}".format(len(ps)), "\n".join(body), faq, None, "website", ld), "1.0")
    idx = [[p["name"], "/place/%s/" % p["id"], p["typ"], (p["sido"] + " " + p["sgg"]).strip(), ""] for p in ps]
    (OUT / "search_index.json").write_text(json.dumps(idx, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    pages_static()
    finish()


def pages_static():
    body = ['<div class="page-head"><h1>숙소 고르는 방법과 이용 안내</h1></div>', ad(),
            '<h2 class="group-title">1. 숙소 찾기</h2><ol class="lead"><li><a href="/region/">지역별</a>, <a href="/type/">유형별</a>, <a href="/feature/">편의시설별</a>로 후보를 좁힙니다.</li><li>숙소 상세에서 체크인·체크아웃 시간, 객실 수, 환불 규정을 확인합니다.</li><li>지도 버튼으로 위치를 보고, 예약 전에 숙소에 최신 정보를 확인합니다.</li></ol>',
            '<h2 class="group-title">2. 정보 읽는 법</h2><ul class="lead"><li><b>체크인·체크아웃</b>은 사업자가 등록한 기본 시간이며 성수기·객실에 따라 달라질 수 있습니다.</li><li><b>환불 규정</b>은 등록 당시 문구이므로 예약 시점의 약관을 꼭 다시 확인하세요.</li><li><b>유형 분류</b>는 상호 키워드로 자동 분류한 것이라 일부는 실제와 다를 수 있습니다.</li></ul>',
            '<div class="note-box">이 사이트는 한국관광공사 공개 데이터를 정리한 참고용이며 숙소의 현재 영업·예약 상태를 보장하지 않습니다. 전체 숙박업소 현황은 <a href="https://wooastay.wooahouse.com">우아숙박</a>에서 볼 수 있습니다.</div>']
    write("/guide/", layout("/guide/", "숙소 고르는 방법과 이용 안내", "지역·유형·편의시설별로 숙소를 찾고 체크인·환불 규정 정보를 읽는 방법을 정리했습니다.", "\n".join(body), None, [("홈", "/"), ("이용 안내", "/guide/")]), "0.4")
    body = ['<div class="page-head"><h1>데이터 설명</h1></div>', '<p class="lead">우아숙소는 한국관광공사 <b>TourAPI 국문 관광정보</b>(공공데이터포털)의 숙박(콘텐츠 유형 32) 정보를 정리합니다. 객실 수·객실 유형·체크인·체크아웃·환불 규정·부대시설·주차·문의 전화는 사업자가 등록한 값이며, 매일 일부씩 수집해 페이지를 늘려 갑니다. 체크인·객실 정보가 모두 비어 있는 숙소는 싣지 않았고, 사진은 사용하지 않습니다.</p>']
    write("/about/", layout("/about/", "데이터 설명", "우아숙소가 사용하는 한국관광공사 TourAPI 숙박 데이터와 정리 방법을 설명합니다.", "\n".join(body), None, [("홈", "/"), ("데이터 설명", "/about/")]), "0.3")
    body = ['<div class="page-head"><h1>개인정보처리방침</h1></div>', '<p class="lead">우아숙소는 회원가입·로그인 없이 이용하며 개인정보를 수집하지 않습니다. 사이트 개선을 위해 Google Analytics를 사용하고, 광고 게재를 위해 Google AdSense와 쿠팡 파트너스를 사용하며 이 과정에서 쿠키가 사용될 수 있습니다.</p>']
    write("/privacy/", layout("/privacy/", "개인정보처리방침", "우아숙소 개인정보처리방침", "\n".join(body), None, [("홈", "/"), ("개인정보처리방침", "/privacy/")]), sitemap=False)


def finish():
    shutil.copytree(ROOT / "assets", OUT / "assets")
    for nf in ROOT.glob("naver*.html"):
        shutil.copy(nf, OUT / nf.name)
    today = TODAY.isoformat()
    urls = "".join("<url><loc>%s%s</loc><lastmod>%s</lastmod><priority>%s</priority></url>" % (BASE, q(p), today, pr) for p, pr in WRITTEN)
    (OUT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</urlset>\n' % urls, encoding="utf-8")
    (OUT / "robots.txt").write_text("User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % BASE, encoding="utf-8")
    (OUT / "CNAME").write_text("wooasukso.wooahouse.com\n", encoding="utf-8")
    nf = layout("/404.html", "페이지를 찾을 수 없습니다", "요청한 페이지를 찾을 수 없습니다.", '<div class="page-head"><h1>페이지를 찾을 수 없습니다</h1></div><div class="chips"><a class="chip" href="/">홈으로</a><a class="chip" href="/type/">유형별</a><a class="chip" href="/region/">지역별</a></div>', None, None, noindex=True)
    (OUT / "404.html").write_text(nf, encoding="utf-8")
    print("페이지", len(WRITTEN), "(sitemap)")


if __name__ == "__main__":
    build()
