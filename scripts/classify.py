#!/usr/bin/env python3
"""Turn fetcher output into page records with a verdict.

Usage: python3 classify.py YYYY-MM-DD out_g/tenders.json out_b/tenders.json out_a/tenders.json
Writes data/days.json (adds/replaces the day, keeps the latest 30 days).

If the ANTHROPIC_API_KEY environment variable is set, each notice is judged by
Claude (model from CLAUDE_MODEL, default claude-sonnet-5-5). Otherwise rule-based
verdicts are used (rougher: more false alarms).
"""
import json, os, re, sys, time
import requests

DAY = sys.argv[1]
SRC = sys.argv[2:]
DATA = os.path.join(os.path.dirname(__file__), "..", "data", "days.json")
KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
MON = {"հունվար": 1, "փետրվար": 2, "մարտ": 3, "ապրիլ": 4, "մայիս": 5, "հունիս": 6, "հուլիս": 7,
       "օգոստոս": 8, "սեպտեմբեր": 9, "հոկտեմբեր": 10, "նոյեմբեր": 11, "դեկտեմբեր": 12}

def norm(s): return re.sub(r"\s+", " ", s or "").strip()

def appr_date(t):
    t = (t or "").lower(); y = re.search(r"20\d\d", t)
    for k, v in MON.items():
        m = re.search(k + r"\w*\W{0,6}(\d{1,2})", t)
        if m and y: return f"{y.group(0)}-{v:02d}-{int(m.group(1)):02d}"
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(20\d\d)", t)
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else ""

def short_cust(c):
    c = norm(c).strip(" «»\"“”")
    return re.sub(r"\s*-?\s*(ը|ն)$", "", c)[:110]

def subj_of(r):
    t = r.get("title", "")
    m = re.findall(r"[«\"“]([^»\"”]{3,90})[»\"”]", t)
    m = [x for x in m if not re.search(r"ԳՀ|ԷԱՃ|ԲՄ|ԱՊՁԲ|ԾՁԲ|\d{2}/\d", x)]
    if m and r.get("kind") != "gnanshum": return norm(m[-1])[:100]
    s = norm(r.get("subj"))
    if s: return (s[0].upper() + s[1:])[:110]
    m = re.search(r"(?:համար[`՝]?\s+)(.{5,120}?)\s+(?:ձեռքբեր|ձեռք բեր|գնման|մատակար)", t)
    return norm(m.group(1) if m else t)[:110]

def items_of(r):
    out = []
    for x in r.get("items", []):
        if re.search(r"Տես|ստորև|ՀՀ դրամ|կից|Համաձայն|^\W*$", x): continue
        out.append(norm(x)[:45])
    return out[:3]

# ---------- rule-based verdict ----------
NOT_BRAND = set("""CHIPSET CACHE GRAPHICS COOLER CASE PSU ARGB XGA DLP MAF ADF DAF FLAP DISC ZIRCONIA ALUMINA GRIT FIBERGLASS XPS AWS INOX
SODIUM HYPOCHLORITE ACICLOVIR VALACICLOVIR PARACETAMOL AMINOPHYLLINE ACETYLCYSTEINE THIOCTIC THIOSULFATE NIFEDIPINE BOROSILICATE CAPS MASK CPAP
CLASS QUICK REFRACTION MODE MIRE FOURIER IOP GENTLE AIR PUFF FIBER OPTIC DOWNLOAD UPLOAD REAL PUBLIC SCREEN TFT DIRECT BACKLIGHT MOHS DIAGONAL
RESOLUTION ULTRA ASPECT RATIO NUMPAD TWAIN WIA HI-SPEED VISTA MAC REACH IMPRESSIONS ENGAGEMENT RATE CALL-TO-ACTION CTA HTML5 GPRS GPU NEURAL ENGINE
UNIFIED MEMORY OTW PEBA RESPONSIVE UNI VVIR VVI VVT VOOR VOO AAI AAIR PTFE SMS MARK FDA MDA ISO13485 ISO9001 CPDA-1 SAGM LCF HOLDER PFO PRIMING PRIME HVR
DEBAKEY COOLEY GIGLI LISTON PHILOS LISS SPLIT REF PRO CARBON RPR ANTI TPO TGA CEA AFP FERRITIN FSH PROLACTIN CANCER VITAMIN FOR IN VITRO DIAGNOSTIC
DELTA RESET UEFA OUTDOR XXL XXXL PRIMALOFT FIVB DIMPLE CR-V LED-BACKLIGHT FULL-HD SMART POINT SOURCE MINI GOOGLE STEVENS BULLDOG CLAMP""".split())
COMPAT = re.compile(r"համար\s+նախատեսված|համատեղելի|սարքի\s+համար|վերլուծիչի\s+համար|կիրառելի\s+լինի|նախատեսված\s+է\s+\S+\s+սարք|для\s+анализатора|совместим", re.I)
OK_NEAR = re.compile(r"կամ\s+համարժեք|կամ\s+նմանատիպ|օրինակ|կամ\s+դրան\s+համարժեք|или\s+эквивалент", re.I)
MUST = re.compile(r"պարտավոր\s+է\s+օգտագործել[^։]{0,120}(ապրանքանիշ|\b[A-Z]{3,}\b)|միայն\s+\S+\s+ապրանքանիշ|Արտադրող[ը]?\s*[`՝:]?\s*[A-Z]{2,}|Մոդել\s*/\s*REF")
EN = set("""DISPLAY COLORS COLOURS BRIGHTNESS VIEWING ANGLE WORKPLACE ROOMS LARGE MEETINGS PHONE WEBINARS PREMIUM DUPLEX ASIA IRAN ERITREA GOOD
CONTRAST TOUCH POINTS INTERACTIVE SYSTEM BOARD STANDARD BASIC ADVANCED PLUS MAX LITE SERIES MODEL TYPE VERSION LICENSE ANNUAL MONTHLY SUPPORT
SERVICE CLOUD SERVER CLIENT USER USERS ADMIN STORAGE NETWORK SECURITY BACKUP POWER SUPPLY INPUT OUTPUT LEVEL HIGH LOW MEDIUM SIZE WEIGHT COLOR
BLACK WHITE GREY GRAY BLUE RED GREEN YELLOW OFFICE HOME BUSINESS EDITION SINGLE DOUBLE DUAL QUAD CORE THREAD SPEED FAST SLOW TOTAL NET GROSS
HDMI-OUT RJ-45 USB-A USB-B MICRO NANO SLIM COMPACT PORTABLE WIRELESS WIRED DIGITAL ANALOG ANALOGUE AUTO MANUAL FRONT BACK REAR TOP BOTTOM
WINDOWS LINUX ANDROID IOS MACOS RYZEN INTEL CORE CELERON PENTIUM XEON ATHLON""".split())
def brandish(w):
    u = w.upper().strip(".-")
    if u in NOT_BRAND or u in EN or len(u) < 3: return False
    if re.search(r"\d.*-|-\d|^[IVX]+-|\.(rar|zip|docx?|xlsx?)$|-$", w, re.I): return False
    return True

def rule_verdict(r):
    if not r.get("spec_len"): return "na", "Բնութագիրը ավտոմատ չգտնվեց կամ ֆայլերը չբացվեցին։"
    sp = re.sub(r"\[(ՖԱՅԼ|XLSX)[^\]]*\]", " ", r.get("spec", ""))
    if MUST.search(sp):
        m = MUST.search(sp); return "risk", "Պահանջվում են կոնկրետ ապրանքանիշ/արտադրող՝ «" + norm(sp[m.start(): m.start() + 110]) + "…»։"
    risky, compat = [], []
    for w in r.get("brands", []):
        if not brandish(w): continue
        i = sp.find(w)
        if i < 0: continue
        ctx = sp[max(0, i - 160): i + 160]
        if OK_NEAR.search(ctx): continue
        after = sp[i: i + 70]
        (compat if (COMPAT.search(ctx) or re.search(r"համար|для|for\s", after)) else risky).append(w)
    if risky:
        return "risk", "Բնութագրում նշված են ապրանքանիշ/մոդել՝ " + ", ".join(dict.fromkeys(risky[:5])) + ", առանց «կամ համարժեք» (ավտոմատ գնահատում, ստուգեք)։"
    if compat:
        return "warn", "Պահանջը կապված է կոնկրետ սարքի/համակարգի հետ՝ " + ", ".join(dict.fromkeys(compat[:4])) + " (համատեղելիություն)։"
    m = re.search(r"ցանկալի[^։|]{0,60}\b[A-Z][A-Za-z]{2,}", sp)
    if m: return "warn", "Ապրանքանիշը նշված է որպես «ցանկալի»՝ «" + norm(m.group(0)) + "»։"
    return "ok", ""

# ---------- Claude verdict ----------
PROMPT = """You judge whether an Armenian public procurement technical specification is discriminatory.
Return ONLY JSON: {"v":"risk|warn|ok|na","note":"one Armenian sentence (empty for plain ok)","subj":"short Armenian subject","cust":"short customer name","items":["≤3 short item names"]}.
risk = specific brand/model/manufacturer/catalog number/origin required without «կամ համարժեք», mandatory brand list, or spec only one brand can meet.
warn = restrictive but possibly justified: reagents/spare parts for an existing device, compatibility with existing systems, «ցանկալի» brand, proprietary OS/printer language, brand drug name next to INN, specific software/SaaS.
ok = nothing found; brands only as examples or with «կամ համարժեք»/«կամ նմանատիպ»; customer's own equipment; standards (ISO, CE, FDA, SAE, API, EAC, hygiene norms); medical eponyms; «առնվազն <model>» performance floor; template column header «ապրանքային նշանը, արտադրողի անվանումը» is NOT evidence.
na = no specification text available.
"""

def claude_verdict(r):
    body = dict(kind=r.get("kind"), title=r.get("title"), customer=r.get("cust"), subject=r.get("subj"),
                brand_contexts=r.get("brand_ctx", [])[:8], keyword_counts=r.get("kw"), spec_excerpt=(r.get("spec") or "")[:7000])
    for i in range(3):
        try:
            res = requests.post("https://api.anthropic.com/v1/messages", timeout=120, headers={
                "x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json=dict(model=MODEL, max_tokens=600, system=PROMPT,
                          messages=[{"role": "user", "content": json.dumps(body, ensure_ascii=False)}]))
            res.raise_for_status()
            txt = res.json()["content"][0]["text"]
            j = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
            if j.get("v") in ("risk", "warn", "ok", "na"): return j
        except Exception as e:
            print("claude error:", str(e)[:150], file=sys.stderr); time.sleep(5 * (i + 1))
    return None

def main():
    recs = []
    for p in SRC:
        if os.path.exists(p): recs += json.load(open(p))
    if not recs:
        print("no notices for", DAY); return 0
    counters = {"gnanshum": 0, "bac": 100, "achurd": 200}
    out = []
    for r in recs:
        kind = r.get("kind", "gnanshum"); counters[kind] += 1
        v, note = rule_verdict(r)
        subj, cust, items = subj_of(r), short_cust(r.get("cust") or ""), items_of(r)
        if KEY and r.get("spec_len"):
            j = claude_verdict(r)
            if j:
                v, note = j["v"], j.get("note", "")
                subj = j.get("subj") or subj; cust = j.get("cust") or cust; items = j.get("items") or items
        ea = r.get("ea") or {}
        out.append(dict(k=counters[kind], kind=kind, code=norm(r.get("code"))[:60] or "—", cust=cust or "—", subj=subj,
                        appr=appr_date(r.get("appr")), items=items[:3], v=v, note=note, pub=r.get("pub", ""),
                        dl=(ea.get("deadline") or r.get("dl") or "")[:16], src=r.get("src", ""), url=r.get("url") or r.get("href")))
    data = json.load(open(DATA)) if os.path.exists(DATA) else {"days": []}
    old = next((d for d in data["days"] if d["date"] == DAY), None)
    if os.environ.get("BACKFILL") and old and len(old["tenders"]) >= len(out):
        print("backfill: existing day has", len(old["tenders"]), ">=", len(out), "- kept"); return 0
    days = [d for d in data["days"] if d["date"] != DAY] + [{"date": DAY, "tenders": out}]
    data["days"] = sorted(days, key=lambda d: d["date"])[-30:]
    json.dump(data, open(DATA, "w"), ensure_ascii=False)
    from collections import Counter
    print(DAY, len(out), dict(Counter(t["v"] for t in out)), "claude" if KEY else "rules")
    return 0

if __name__ == "__main__":
    sys.exit(main())
