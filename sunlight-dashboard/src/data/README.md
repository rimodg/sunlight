# Country metadata

`countries.json` is a derived database from **world-countries 5.1.0**, by the [mledoze/countries contributors](https://github.com/mledoze/countries). It retains common/official names, ISO identifiers, country reference coordinates and translated/common aliases. Duplicate aliases are removed. It is not procurement or trade data and does not certify boundaries or sovereignty.

This derived database and `code/watch_country_codes.json` remain licensed under the [Open Database License 1.0](COUNTRIES-LICENSE.txt). This license applies to these data files, not the surrounding application code. The original license text is included with line endings and trailing whitespace normalized. The application offers downloads of the derived catalog and license in **Trade data & sources**.

Regenerate from the pinned package/lockfile with:

```sh
cd sunlight-dashboard
npm ci
node scripts/generate-country-catalog.mjs
```

The map's separate country geometry is Natural Earth 4.1.0 / world-atlas 2.0.2. Country reference points are schematic endpoints, not ports, shipping routes or measured project coordinates. UN Comtrade reporting areas may have different definitions; the source reporter/partner names and numeric codes remain attached to trade links.
