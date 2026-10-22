"""Share the existing ODbL country catalog with the backend research resolver."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    rows=json.loads((ROOT/'sunlight-dashboard/src/data/countries.json').read_text())
    output=[{k:r[k] for k in ('name','official','code','alpha3','numeric','aliases')} for r in rows]
    (ROOT/'code/research_countries.json').write_text(json.dumps(output,ensure_ascii=False,separators=(',',':'))+'\n')
    (ROOT/'code/RESEARCH-COUNTRIES-LICENSE.txt').write_text((ROOT/'sunlight-dashboard/src/data/COUNTRIES-LICENSE.txt').read_text())
    print({'countries':len(output),'source':'world-countries 5.1.0, derived ODbL catalog'})
