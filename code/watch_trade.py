"""Bounded, cached public UN Comtrade preview. Never a global procurement feed."""
from __future__ import annotations

import asyncio
import json
import math
import os
import time
import hashlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from connectivity import offline_enabled, state_directory

ENDPOINT = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
PERIOD = "2023"
# Selected reporting economies, not worldwide coverage. Comtrade uses 699 for India.
REPORTERS = (842, 156, 276, 392, 826, 251, 699, 528, 76, 710)
COUNTRIES = {n for n in json.loads(Path(__file__).with_name("watch_country_codes.json").read_text()) if n > 0}


def country_code(value):
    try:
        if isinstance(value, bool) or str(value).strip() != str(int(value)):
            return None
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    number = {842: 840, 699: 356, 251: 250, 381: 380, 579: 578, 757: 756}.get(number, number)
    return number if number in COUNTRIES else None


def parse_reporter(payload, reporter):
    """Filter exact annual total-goods exports; exclude aggregates and duplicates."""
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("Unexpected source schema")
    routes = {}
    for row in payload["data"]:
        if not isinstance(row, dict):
            continue
        if str(row.get("period")) != PERIOD or row.get("flowCode") != "X" or row.get("cmdCode") != "TOTAL":
            continue
        origin, destination = country_code(row.get("reporterCode")), country_code(row.get("partnerCode"))
        if origin != country_code(reporter) or destination is None or origin == destination:
            continue
        value = row.get("primaryValue")
        if isinstance(value, bool) or not isinstance(value, (float, int)) or value <= 0 or value > 9_007_199_254_740_991 or not math.isfinite(value):
            continue
        # Do not combine multiple customs/mode/partner2 slices as bilateral totals.
        if row.get("partner2Code", 0) != 0 or row.get("customsCode", "C00") != "C00" or str(row.get("motCode", 0)) != "0":
            continue
        key = (origin, destination)
        result = {"reporter": origin, "partner": destination, "usd": value,
                  "period": PERIOD, "reported": row.get("isReported"), "source_reporter": reporter,
                  "source_partner": row.get("partnerCode"), "reporter_name": row.get("reporterDesc"), "partner_name": row.get("partnerDesc")}
        if key in routes and routes[key]["usd"] != value:
            raise ValueError("Conflicting duplicate bilateral totals")
        routes[key] = result
    return list(routes.values())


class TradeFeed:
    def __init__(self, transport=None, reporters=None, persist=False):
        self.transport = transport
        self.reporters = reporters
        self.lock = asyncio.Lock()
        self.cached = None
        self.expires = 0
        self.persist = persist

    def cache_path(self):
        name = 'global' if not self.reporters else '-'.join(str(int(r)) for r in self.reporters)
        return state_directory()/'trade-cache'/(name+'.json')

    def load_cached(self):
        if self.cached is not None or not self.persist:return self.cached
        try:
            path=self.cache_path()
            if path.stat().st_size>4*1024*1024:return None
            wrapper=json.loads(path.read_text());payload=wrapper['payload']
            raw=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
            if hashlib.sha256(raw).hexdigest()!=wrapper['sha256']:return None
            if payload.get('schema_version')!='sunlight.trade-preview.v1' or payload.get('source_url')!=ENDPOINT or payload.get('period')!=PERIOD:return None
            if payload.get('reporters_requested')!=list(self.reporters or REPORTERS):return None
            if not isinstance(payload.get('routes'),list) or len(payload['routes'])>5000:return None
            for r in payload['routes']:
                if not country_code(r['reporter']) or not country_code(r['partner']) or not math.isfinite(r['usd']) or r['usd']<=0 or r['period']!=PERIOD:return None
            self.cached=payload
        except (OSError,ValueError,TypeError,KeyError):
            return None
        return self.cached

    def save_cached(self):
        if not self.persist or not self.cached.get('routes'):return
        raw=json.dumps(self.cached,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        target=self.cache_path();target.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w',dir=target.parent,delete=False) as f:
            temp=Path(f.name);json.dump({'sha256':hashlib.sha256(raw).hexdigest(),'payload':self.cached},f)
        try:os.replace(temp,target)
        finally:temp.unlink(missing_ok=True)

    async def get(self):
        async with self.lock:
            self.load_cached()
            if offline_enabled():
                if self.cached and self.cached.get('routes'):
                    return {**self.cached,'status':'offline_cached','offline':True,'refresh_performed':False,
                            'coverage':self.cached['coverage']+' Offline retained extract; fetched_at remains the actual last retrieval time.'}
                return {'schema_version':'sunlight.trade-preview.v1','source':'UN Comtrade public preview',
                        'source_url':ENDPOINT,'period':PERIOD,'currency':'USD','status':'unavailable',
                        'offline':True,'refresh_performed':False,'fetched_at':None,'attempted_at':None,
                        'routes':[],'errors':[],'coverage':'Offline mode. No retained trade preview exists for this scope. Missing routes are unknown; other packaged source layers remain available.'}
            if self.cached is not None and time.monotonic() < self.expires:
                return self.cached
            now = datetime.now(timezone.utc).isoformat()
            async with httpx.AsyncClient(timeout=12, transport=self.transport, follow_redirects=False) as client:
                async def fetch(reporter):
                    params = dict(period=PERIOD, reporterCode=reporter, cmdCode="TOTAL", flowCode="X",
                                  partner2Code=0, customsCode="C00", motCode=0, maxRecords=500)
                    try:
                        response = await client.get(ENDPOINT, params=params)
                        response.raise_for_status()
                        rows = parse_reporter(response.json(), reporter)
                        return reporter, rows, None if rows else "No usable bilateral totals returned"
                    except (httpx.HTTPError, ValueError) as exc:
                        reason = f"HTTP {exc.response.status_code}" if isinstance(exc, httpx.HTTPStatusError) else "Source unavailable or invalid response"
                        return reporter, [], reason
                reporters = self.reporters or REPORTERS
                outcomes = await asyncio.gather(*(fetch(code) for code in reporters))
            routes, errors, available = [], [], []
            for reporter, rows, error in outcomes:
                if error:
                    errors.append({"reporter": reporter, "reason": error})
                else:
                    available.append(reporter)
                    routes.extend(rows)
            stale = False
            fetched_at = now
            if not routes and self.cached and self.cached["routes"]:
                routes, fetched_at, stale = self.cached["routes"], self.cached["fetched_at"], True
            self.cached = {
                "schema_version": "sunlight.trade-preview.v1", "source": "UN Comtrade public preview",
                "source_url": ENDPOINT, "documentation_url": "https://comtradeapi.un.org/",
                "period": PERIOD, "currency": "USD", "flow": "Reported annual total-goods exports",
                "status": "stale" if stale else "partial" if routes else "unavailable",
                "fetched_at": fetched_at if routes else None, "attempted_at": now,
                "reporters_requested": list(reporters), "reporters_available": available,
                "coverage": "Selected reporters only; public preview capped at 500 rows per reporter. Not global coverage or real-time shipments. Not procurement spending.",
                "routes": sorted(routes, key=lambda r: (-r["usd"], r["reporter"], r["partner"])), "errors": errors,
            }
            self.expires = time.monotonic() + (3600 if errors else 43200)
            try:self.save_cached()
            except OSError:self.cached['persistence_warning']='Trade preview could not be saved for restart; this response is retained in memory only.'
            return self.cached


feed = TradeFeed(persist=True)
country_feeds = {}
router = APIRouter()


@router.get("/watch-data/context")
async def procurement_context():
    """Deployment-supplied estimate, kept separate from observed documents."""
    from urllib.parse import urlparse
    try:
        amount = float(os.environ.get("SUNLIGHT_PROCUREMENT_ANNUAL_ESTIMATE", ""))
        year = int(os.environ.get("SUNLIGHT_PROCUREMENT_ESTIMATE_YEAR", ""))
        currency = os.environ.get("SUNLIGHT_PROCUREMENT_ESTIMATE_CURRENCY", "USD")
        url = os.environ.get("SUNLIGHT_PROCUREMENT_ESTIMATE_SOURCE_URL", "")
        title = os.environ.get("SUNLIGHT_PROCUREMENT_ESTIMATE_SOURCE_TITLE", "")
        if not math.isfinite(amount) or amount <= 0 or not 1900 <= year <= datetime.now(timezone.utc).year or len(currency) != 3 or not currency.isalpha() or currency != currency.upper() or urlparse(url).scheme != "https" or not urlparse(url).netloc or not title:
            raise ValueError("Invalid context configuration")
    except (ValueError, OverflowError):
        return {"status": "not_configured", "annual_estimate": None,
                "note": "No sourced annual procurement estimate configured. No worldwide spending counter is asserted."}
    return {"status": "configured", "annual_estimate": {"amount": amount, "year": year, "currency": currency, "source_url": url, "source_title": title},
            "note": "Deployment-supplied annual estimate. A uniform current-year pace is modeled context, not observed spending. The source is not independently validated by this endpoint."}


@router.get("/watch-data/trade")
async def trade_preview(reporter: int | None = None):
    if reporter is None:
        return await feed.get()
    country = country_code(reporter)
    if country is None:
        raise HTTPException(status_code=422, detail='A recognized country numeric code is required')
    source_code = {840: 842, 356: 699, 250: 251, 380: 381, 578: 579, 756: 757}.get(country, country)
    if source_code not in country_feeds:
        country_feeds[source_code] = TradeFeed(reporters=(source_code,),persist=True)
    return await country_feeds[source_code].get()
