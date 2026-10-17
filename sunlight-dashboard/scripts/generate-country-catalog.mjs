// Country metadata only. The derived database remains under ODbL; see src/data/README.md.
import countries from 'world-countries';
import {writeFileSync,readFileSync} from 'node:fs';
const catalog=countries.map(c=>({name:c.name.common,official:c.name.official,code:c.cca2,alpha3:c.cca3,numeric:c.ccn3,center:[c.latlng[1],c.latlng[0]],aliases:[...new Set([...c.altSpellings,...Object.values(c.translations).map(t=>t.common)])]}));
writeFileSync(new URL('../src/data/countries.json',import.meta.url),JSON.stringify(catalog)+'\n');
writeFileSync(new URL('../../code/watch_country_codes.json',import.meta.url),JSON.stringify(countries.map(c=>Number(c.ccn3)).filter(n=>n>0))+'\n');
writeFileSync(new URL('../src/data/COUNTRIES-LICENSE.txt',import.meta.url),readFileSync(new URL('../node_modules/world-countries/LICENSE',import.meta.url),'utf8').replace(/\r\n/g,'\n').replace(/[ \t]+$/gm,''));
