#!/usr/bin/env python3
"""Daily fetcher for gnumner.minfin.am quotation requests (գնանշման հարցում).

Usage: python3 fetch_tenders.py YYYY-MM-DD [outdir] [kinds]
kinds: comma list of gnanshum,bac,achurd (default all three)
Writes outdir/tenders.json: one record per tender published on that date with
header fields, technical-spec text and heuristic brand/equivalence flags.
Needs: requests, bs4; bsdtar (RAR/ZIP) and catdoc (.doc) improve coverage.
"""
import io, json, os, re, subprocess, sys, tempfile, zipfile, html
from urllib.parse import quote, urljoin
import requests
from bs4 import BeautifulSoup

DAY = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else "out"
KINDS = (sys.argv[3] if len(sys.argv) > 3 else "gnanshum,bac,achurd").split(",")
CATS = {"gnanshum": "gnanshman_harcman_haytararutyun_ev_hraver",
        "bac": "bac_mrcuyti_haytararutyun_ev_hraver",
        "achurd": "elektronayin_achurdi_haytararutyun_ev_hraver"}
os.makedirs(OUT, exist_ok=True)
BASE = "https://gnumner.minfin.am/hy/page/gnanshman_harcman_haytararutyun_ev_hraver/"
INTER = "http://crt.sectigo.com/GoGetSSLRSADVSSLCA2.crt"  # gnumner omits its intermediate cert

def ca_bundle():
    p = os.path.join(tempfile.gettempdir(), "gnum-bundle.pem")
    if not os.path.exists(p):
        der = requests.get(INTER, timeout=30).content
        pem = subprocess.run(["openssl", "x509", "-inform", "DER"], input=der, capture_output=True, check=True).stdout
        sysb = next(f for f in ["/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt"] if os.path.exists(f))
        open(p, "wb").write(open(sysb, "rb").read() + b"\n" + pem)
    return p

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (tender-digest)"
CA = ca_bundle()

import time
def get(url, **kw):
    v = CA if "gnumner.minfin.am" in url else True
    for i in range(4):
        try:
            r = S.get(url, timeout=90, verify=v, **kw)
        except requests.exceptions.ConnectionError:
            if i == 3: raise
            time.sleep(3 + 4 * i); continue
        if r.status_code < 500 or i == 3: break
        time.sleep(3 + 4 * i)
    r.raise_for_status(); return r

# ---------- text extraction ----------
def docx_text(b):
    try:
        z = zipfile.ZipFile(io.BytesIO(b)); x = z.read("word/document.xml").decode("utf8", "ignore")
    except Exception:
        return ""
    x = x.replace("<w:tab/>", "\t"); x = re.sub(r"</w:p>", "\n", x); x = re.sub(r"</w:tc>", " | ", x); x = re.sub(r"</w:tr>", "\n", x)
    return html.unescape(re.sub(r"<[^>]+>", "", x))

def xlsx_text(b):
    try:
        z = zipfile.ZipFile(io.BytesIO(b))
    except Exception:
        return ""
    ss = []
    if "xl/sharedStrings.xml" in z.namelist():
        ss = [re.sub(r"<[^>]+>", "", m) for m in re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode("utf8", "ignore"), re.S)]
    out = []
    for n in sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)):
        x = z.read(n).decode("utf8", "ignore")
        for row in re.findall(r"<row[^>]*>(.*?)</row>", x, re.S):
            cells = []
            for attrs, inner in re.findall(r"<c([^>]*?)(?:/>|>(.*?)</c>)", row, re.S):
                v = re.search(r"<v>(.*?)</v>", inner or ""); t = re.search(r"<t[^>]*>(.*?)</t>", inner or "", re.S)
                if 't="s"' in attrs and v: cells.append(ss[int(v.group(1))] if int(v.group(1)) < len(ss) else "")
                elif v: cells.append(v.group(1))
                elif t: cells.append(t.group(1))
            cells = [c for c in cells if c]
            if cells: out.append(" | ".join(cells))
    return html.unescape("\n".join(out))

def doc_text(b):
    try:
        r = subprocess.run(["catdoc", "-d", "utf-8", "-w"], input=b, capture_output=True, timeout=60)
        t = r.stdout.decode("utf8", "ignore")
        if len(re.findall(r"[\u0531-\u0586]", t)) > 200: return t
    except Exception:
        pass
    best = ""
    for off in (0, 1):  # fallback: UTF-16LE runs
        s = b[off:]; s = s[: len(s) // 2 * 2]
        txt = s.decode("utf-16-le", "ignore")
        runs = re.findall(r"[\x20-\x7e\u0530-\u058f\u0400-\u04ff\r\x07\t«»–—’“”№\xa0․՝]{20,}", txt)
        cand = "\n".join(r for r in runs if re.search(r"[\u0530-\u058f]", r))
        if len(cand) > len(best): best = cand
    return best.replace("\x07", " | ").replace("\r", "\n")

def archive_members(b, name):
    """Return list of (member_name, bytes) for zip/rar using zipfile or bsdtar."""
    out = []
    if b[:2] == b"PK":
        try:
            z = zipfile.ZipFile(io.BytesIO(b))
            for n in z.namelist():
                if not n.endswith("/"):
                    try: fn = n.encode("cp437").decode("utf8")
                    except Exception: fn = n
                    out.append((fn, z.read(n)))
            return out
        except Exception:
            pass
    with tempfile.TemporaryDirectory() as d:
        ap = os.path.join(d, "a.bin"); open(ap, "wb").write(b)
        ex = os.path.join(d, "x"); os.makedirs(ex)
        subprocess.run(["bsdtar", "-xf", ap, "-C", ex], capture_output=True, timeout=120)
        for root, _, files in os.walk(ex):
            for f in files:
                p = os.path.join(root, f); out.append((os.path.relpath(p, ex), open(p, "rb").read()))
    return out

def file_text(name, b):
    n = name.lower()
    if b[:2] == b"PK" and (n.endswith(".docx") or b"word/document.xml" in b[:4000] or n.endswith(".docx")):
        return docx_text(b)
    if n.endswith(".xlsx"): return xlsx_text(b)
    if n.endswith(".xls"):
        try:
            import xlrd
            wb = xlrd.open_workbook(file_contents=b); out = []
            for sh in wb.sheets():
                for r in range(sh.nrows):
                    cells = [str(c.value).strip() for c in sh.row(r) if str(c.value).strip()]
                    if cells: out.append(" | ".join(cells))
            return "\n".join(out)
        except Exception:
            return ""
    if b[:4] == b"\xd0\xcf\x11\xe0" and n.endswith(".doc"): return doc_text(b)
    return ""

LANG_BAD = re.compile(r"eng|angl|rus|ռուս|անգլ|announcement|объявл|приглаш|услуг|англ|русс|Rus/|angleren|ruseren", re.I)
LANG_GOOD = re.compile(r"arm|hay|հրավեր|hraver|carayutyun|apranq|ծառայ|հայերեն|Arm/", re.I)
def score(n):
    s = 0
    if re.search(r"\.(xml|pdf|jpe?g|png)$", n, re.I): s -= 50
    if re.search(r"\.xlsx?$", n, re.I): s -= 20
    if LANG_BAD.search(n): s -= 10
    if LANG_GOOD.search(n): s += 5
    if re.search(r"[\u0531-\u0586]", n): s += 2
    return s

# ---------- field extraction ----------
def norm(s): return re.sub(r"\s+", " ", s or "").strip()
def hdr(tx):
    def g(p):
        m = re.search(p, tx, re.I); return norm(m.group(1))[:250] if m else ""
    return dict(code=g(r"[Ծծ]ածկագիր[ըն]?\s*[`՝:\-–]*\s*[«\"]?([^\n»\"]+)"),
                cust=g(r"Պատվիրատու[ն]?\s*[`՝:]?\s*([^\n]+?)(?:,\s*որը|\n)"),
                appr=g(r"հաստատված\s+է\s+գնահատող\s+հանձնաժողովի\s*([^\n]+)"),
                subj=g(r"կնքել\s+([^\n]{0,160}?)\s+պայմանագ"))

def tech_spec(tx):
    tx = re.sub(r"[ \t\xa0]+", " ", tx); tx = re.sub(r"\s*\n\s*", "\n", tx); tx = re.sub(r"(\s*\|\s*)+", " | ", tx)
    ea = list(re.finditer(r"Ամբողջական անվանումը \| Տեխնիկական բնութագիրը", tx))
    if ea:
        s = tx[ea[-1].start(): ea[-1].start() + 20000]
        e = re.search(r"\n\s*(Հավելված|ՀԱՎԵԼՎԱԾ)\s*N?\s*\d|\nՊԱՅՄԱՆԱԳԻՐ", s[300:])
        return s[: e.start() + 300] if e else s
    ms = list(re.finditer(r"ՏԵԽՆԻԿԱԿԱՆ\s*ԲՆՈՒԹԱԳԻՐ\s*[-–—]?\s*ԳՆՄԱՆ", tx))
    st = None
    if ms: st = ms[-1].start()
    else:
        for m in re.finditer(r"տեխնիկական\s*բնութագիր", tx, re.I):
            if re.search(r"չափման|քանակ|Հ/հ|CPV|միավոր", tx[m.start(): m.start() + 3000], re.I): st = m.start(); break
    if st is None: return ""
    s = tx[st: st + 40000]
    e = re.search(r"\n\s*Հավելված\s*N?\s*\d|\nՀԱՎԵԼՎԱԾ\s*N?\s*\d|\nՊԱՅՄԱՆԱԳԻՐ\s*N", s[200:])
    if e: s = s[: e.start() + 200]
    s = re.sub(r"(\s*\|\s*)+", " | ", s); s = re.sub(r"[ \t]+", " ", s); s = re.sub(r"\n+", "\n", s)
    return s

WL = set("""SAE API ISO GOST USB HDMI LED RAM SSD HDD DDR DDR4 DDR5 CPU PVC ASTM DIN IEC LCD IPS VGA WIFI WI-FI FULL HD GHZ MHZ HZ MBPS DVI FHD UHD RJ45 CE EN JASO ACEA DOT DOT4 ATF SATA PCIE NVME AC DC USB-C TYPE-C TYPE BLUETOOTH CMYK RGB ANSI GMP HACCP CPV PDF GB TB MB KW KVA LTE GSM SIM UPS PC OS IT EU USA SN SL SM SP CF CI CK CJ CH GL LS EP NLGI ROHS OEM WINDOWS OFFICE MICROSOFT LINUX ANDROID WH MAH ML DVD CD ETHERNET LAN WAN POE UTP FTP SFP ABS OLED TN VA ATX MM CM KG HTML JPEG PNG LI-ION NIMH AWG GBPS NFC GPS WLAN AMD INTEL CORE ARM NTFS RAID VESA DISPLAYPORT PPE TU HPLC ELISA PCR DNA RNA HIV EDTA CRP ESR TSH PSA BOD COD UV IR LPG CNG EURO NO SO CO NOX AISI DN PN PE PP PET HDPE LDPE PPR XLPE PEX MDF HDF LDSP DSP OSB ARMEPS XLSX III CAD EXCEL AUTOCAD WORD IPV4 IPV6 VPN MBIT""".split())
def flags(sp):
    words = [w for w in re.findall(r"\b[A-Z][A-Za-z0-9\-\.]{2,}\b", sp) if w.upper().strip(".") not in WL and not re.match(r"^[A-Z]?\d|^[A-Z]{1,2}-?\d|^CPV", w)]
    brands = list(dict.fromkeys(words))[:15]
    ctx = []
    for w in brands[:8]:
        i = sp.find(w); ctx.append(norm(sp[max(0, i - 90): i + 90]))
    kw = {}
    for k, p in {"equiv": r"կամ\s+համարժեք|или\s+эквивалент", "origin": r"(արտադրության|ծագման)\s+երկիր", "desirable": r"ցանկալի",
                 "dealer": r"դիլեր|պաշտոնական\s+ներկայացուցիչ", "model": r"մոդել[ըի]?\s*[`՝:]"}.items():
        kw[k] = len(re.findall(p, sp, re.I))
    return brands, ctx, kw

def items_of(sp):
    its = [norm(m.group(1))[:60] for m in re.finditer(r"\b\d{7,8}(?:/\d+)?\s*\|\s*([^|\n]{3,60})", sp)]
    return [x for x in dict.fromkeys(its) if not re.match(r"^\d|^[-–]$", x)]

# ---------- listing ----------
def listing(kind):
    base = f"https://gnumner.minfin.am/hy/page/{CATS[kind]}/"
    out, p = [], 1
    while p < 60:
        soup = BeautifulSoup(get(base if p == 1 else base + str(p)).text, "html.parser")
        ts = soup.select("div.tender"); older = False
        for t in ts:
            a = t.select_one("a"); tm = t.select_one(".tender_time")
            tt = norm(tm.get_text()) if tm else ""
            m = re.search(r"(\d{4}-\d\d-\d\d) (\d\d:\d\d)", tt)
            if not m: continue
            if m.group(1) == DAY:
                dl = re.search(r"մինչեւ\s+(\d{4}-\d\d-\d\d \d\d:\d\d)", tt)
                out.append(dict(kind=kind, title=norm(a.get_text()), href=a.get("href"), pub=m.group(2),
                                dl=dl.group(1) if dl else ("անժամկետ" if "անժամկետ" in tt else "")))
            elif m.group(1) < DAY: older = True
        if older or not ts: break
        p += 1
    return out

def armeps_docs(href):
    rid = re.search(r"resourceId=(\d+)", href).group(1)
    soup = BeautifulSoup(get(f"https://armeps.am/epps/cft/listContractDocuments.do?resourceId={rid}").text, "html.parser")
    docs = []
    for a in soup.select("a[onclick*=downloadDocForAnonymous]"):
        did = re.search(r"\d+", a["onclick"]).group(0)
        docs.append((norm(a.get_text()), f"https://armeps.am/epps/cft/downloadContractDocument.do?documentId={did}&resourceId=null"))
    return docs

def eauction(href, rec):
    soup = BeautifulSoup(get(href).text, "html.parser")
    txt = soup.get_text("\n")
    def f(lbl):
        m = re.search(lbl + r"\s*\n+\s*([^\n]+)", txt); return norm(m.group(1)) if m else ""
    rec["ea"] = dict(code=f("Ծածկագիր"), cust=f("Գնորդ"), ptype=f("Գնման տեսակ"), auction=f("Հակադարձ աճուրդ"), deadline=f("Հայտերի ընդունման վերջնաժամկետ"))
    files = []
    for a in soup.select("a[href]"):
        u = urljoin(href, a["href"])
        if re.search(r"\.(zip|rar|docx?|xlsx)$", u, re.I) and "document" in u:
            try:
                b = get(u).content; n = u.rsplit("/", 1)[-1]
                files += archive_members(b, n) if re.search(r"\.(zip|rar)$", n, re.I) else [(n, b)]
            except Exception as e:
                rec.setdefault("warn_files", []).append(f"{u}: {str(e)[:80]}")
    return files

def process(item):
    href = item["href"]; rec = dict(item); files = []
    try:
        if "eauction.armeps.am" in href:
            rec["src"] = "eAuction"; files = eauction(href, rec)
        elif "armeps.am" in href:
            rec["src"] = "ARMEPS"
            docs = sorted(armeps_docs(href), key=lambda d: -score(d[0]))
            for name, u in docs:
                if score(name) <= -50 and not re.search(r"\.(zip|rar)$", name, re.I): continue
                try: b = get(u).content
                except Exception as e:
                    rec.setdefault("warn_files", []).append(f"{name}: {str(e)[:80]}"); continue
                if re.search(r"\.(zip|rar)$", name, re.I): files += [(f"{name}/{n}", x) for n, x in archive_members(b, name)]
                else: files.append((name, b))
                if len(files) >= 8: break
        else:
            rec["src"] = "gnumner"
            b = get(href).content; name = href.rsplit("/", 1)[-1]
            if re.search(r"\.(zip|rar|7z)$", name, re.I): files = archive_members(b, name)
            else: files = [(name, b)]
    except Exception as e:
        rec["err"] = str(e)[:200]
    rec["files"] = [n for n, _ in files]
    best = None; xl = []
    for n, b in sorted(files, key=lambda f: -score(f[0])):
        t = file_text(n, b)
        if n.lower().endswith(".xlsx") and t: xl.append((n, t)); continue
        if len(t) < 3000: continue
        sp = tech_spec(t)
        cand = dict(name=n, tx=t, spec=sp, s=score(n))
        if best is None or (len(sp) > len(best["spec"]) and cand["s"] >= best["s"]) or (not best["spec"] and sp): best = cand
        if cand["s"] > 0 and len(sp) > 300: break
    spec = best["spec"] if best else ""
    tb = [(n, b) for n, b in files if re.search(r"texnikakan|տեխնիկական|bnutagir", n, re.I) and not re.search(r"\.(pdf|jpe?g|png)$", n, re.I)]
    seen = set()
    for n, b in tb:
        if best and n == best["name"]: continue
        h = hash(b)
        if h in seen or len(spec) > 40000: continue
        seen.add(h)
        t = file_text(n, b)
        if not t and re.search(r"\.(zip|rar)$", n, re.I):
            t = "\n".join(file_text(m, x) for m, x in archive_members(b, n))
        if t: spec += f"\n[ՖԱՅԼ {n}]\n" + re.sub(r"[ \t]+", " ", t)[:15000]
    xl = [(n, t) for n, t in xl if not any(n == m for m, _ in tb)]
    if len(spec) < 600 and xl: spec += "".join(f"\n[XLSX {n}]\n{t[:15000]}" for n, t in xl[:2])
    rec.update(hdr(best["tx"]) if best else dict(code="", cust="", appr="", subj=""))
    if rec.get("ea"):
        rec["code"] = rec["ea"]["code"] or rec["code"]; rec["cust"] = rec["ea"]["cust"] or rec["cust"]
    rec["pick"] = best["name"] if best else ""
    spec = spec[:45000]
    brands, ctx, kw = flags(spec)
    rec.update(spec_len=len(spec), items=items_of(spec)[:6], n_items=len(items_of(spec)), brands=brands, brand_ctx=ctx, kw=kw, spec=spec[:20000])
    if "gnumner" in href:
        b0, f0 = href.rsplit("/", 1); rec["url"] = b0 + "/" + quote(f0)
    else:
        rec["url"] = href
    return rec

if __name__ == "__main__":
    items = [it for k in KINDS for it in listing(k)]
    print(f"{DAY}: {len(items)} tenders", file=sys.stderr)
    res = []
    for i, it in enumerate(items, 1):
        try: r = process(it)
        except Exception as e: r = dict(it, err=str(e)[:200], spec="", spec_len=0, brands=[], brand_ctx=[], kw={}, items=[], n_items=0, url=it["href"], code="", cust="", appr="", subj="")
        r["k"] = i; res.append(r)
        print(f"#{i} {r.get('kind')} {r.get('src')} spec={r['spec_len']} brands={len(r['brands'])} {r.get('err','')}", file=sys.stderr)
    json.dump(res, open(os.path.join(OUT, "tenders.json"), "w"), ensure_ascii=False, indent=1)
