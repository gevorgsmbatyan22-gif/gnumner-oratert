# Գնումների օրաթերթ

Ամեն երեկո (23:41, Երևանի ժամով) GitHub Actions-ը հավաքում է gnumner.minfin.am-ում տվյալ օրը հրապարակված
գնանշման հարցումները, բաց մրցույթներն ու էլեկտրոնային աճուրդները, ստուգում տեխնիկական բնութագրերը,
թարմացնում `site/index.html`-ը և հրապարակում այն GitHub Pages-ում։ Առավոտյան 07:41-ին նախորդ օրը կրկին ստուգվում է՝ բացերը լրացնելու համար։

## Կառուցվածք
- `scripts/fetch_tenders.py` — ներբեռնում և մշակում է հրավերները (docx, doc, zip, rar, xlsx, xls)
- `scripts/classify.py` — գնահատում է բնութագրերը (Claude API-ով կամ կանոններով) և թարմացնում `data/days.json`-ը (վերջին 30 օր)
- `scripts/build.py` — `data/days.json` + `scripts/template.html` → `site/index.html`
- `.github/workflows/daily.yml` — ամենօրյա գործարկում
