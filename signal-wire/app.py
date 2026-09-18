#!/usr/bin/env python3
"""Signal Wire's resilient, source-tiered public-feed research pipeline."""
from __future__ import annotations
import hashlib, html, json, os, re, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from analysis import analyse, similar, event_key, why_it_matters_for, relevance_for_score
try:
    from flask import Flask, jsonify, render_template
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, 'data')
CACHE = os.path.join(DATA, 'cache.json')
KNOWLEDGE = os.path.join(DATA, 'knowledge.json')
PORT = int(os.getenv('PORT', '5050'))
TIMEOUT = 12
MAX_PER_SOURCE = 45
RELEVANCE_THRESHOLD = 35
# Some otherwise valid public feeds contain illegal control characters. Strip only
# XML-invalid bytes before parsing; never rewrite article content or URLs.
XML_INVALID = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')

# Public feeds only. A failed optional feed is logged in source_health and never
# stops the other sources. The explicit tier is more trustworthy than guessing
# from a publisher name later in the pipeline.
def feed(name, category, url, tier, enabled=True, note=''):
    return {'name': name, 'category': category, 'url': url, 'tier': tier, 'access': 'public RSS/Atom', 'enabled': enabled, 'note': note}

SOURCES = [
    # Tier 1: official / primary data and releases
    feed('Federal Reserve', 'Macro', 'https://www.federalreserve.gov/feeds/press_all.xml', 'official'),
    feed('FRED', 'Macro', 'https://fredblog.stlouisfed.org/feed/', 'official'),
    feed('BLS', 'Macro', 'https://www.bls.gov/feed/bls_latest.rss', 'official'),
    feed('BEA', 'Macro', 'https://apps.bea.gov/rss/rss.xml', 'official'),
    feed('Census Bureau', 'Macro', 'https://www.census.gov/content/census/en/newsroom/press-releases.xml', 'official'),
    feed('SEC / EDGAR', 'Equities', 'https://www.sec.gov/news/pressreleases.rss', 'official'),
    feed('US Treasury', 'Macro', 'https://home.treasury.gov/news/press-releases', 'official', False, 'No unrestricted Treasury RSS endpoint verified; official press-release page retained for manual verification.'),
    feed('CFTC', 'Commodities', 'https://www.cftc.gov/RSS/RSSGP/rssgp.xml', 'official'),
    feed('New York Fed', 'Macro', 'https://libertystreeteconomics.newyorkfed.org/feed/', 'official'),
    feed('Atlanta Fed', 'Macro', 'https://www.atlantafed.org/rss/pressindex', 'official'),
    feed('Dallas Fed', 'Macro', 'https://www.dallasfed.org/rss/releases.xml', 'official'),
    feed('ECB', 'Macro', 'https://www.ecb.europa.eu/rss/press.html', 'official'),
    feed('Bank of England', 'Macro', 'https://www.bankofengland.co.uk/rss/news', 'official'),
    feed('Bank of Japan', 'Macro', 'https://www.boj.or.jp/en/rss/whatsnew.xml', 'official'),
    feed('Reserve Bank of Australia', 'Macro', 'https://www.rba.gov.au/rss/rss-cb-media-releases.xml', 'official'),
    feed('Reserve Bank of New Zealand', 'Macro', 'https://www.rbnz.govt.nz/rss', 'official', False, 'Public RSS endpoint was not available during audit; official news page remains a verification link.'),
    feed('Bank of Canada', 'Macro', 'https://www.bankofcanada.ca/content_type/press-releases/feed/', 'official'),
    feed('Swiss National Bank', 'Macro', 'https://www.snb.ch/public/rss/en/pressrel', 'official'),
    feed('Norges Bank', 'Macro', 'https://www.norges-bank.no/en/news-events/news/', 'official', False, 'Official news page has no stable unrestricted RSS endpoint verified.'),
    feed('BIS', 'Macro', 'https://www.bis.org/doclist/all_pressrels.rss', 'official'),
    feed('IMF', 'Macro', 'https://www.imf.org/external/rss/feeds.aspx?category=whatsnew_eng', 'official', False, 'IMF feed endpoint returned method-not-allowed during audit; no bypass attempted.'),
    feed('EIA', 'Commodities', 'https://www.eia.gov/rss/todayinenergy.xml', 'official'),
    # Tier 2: major financial and business reporting
    feed('Reuters', 'Macro', 'https://www.reuters.com/my-news/feed/', 'major-financial', False, 'Reuters public feed requires account access; no bypass attempted.'),
    feed('CNBC', 'Equities', 'https://www.cnbc.com/id/100003114/device/rss/rss.html', 'major-financial'),
    feed('Bloomberg Markets', 'Macro', 'https://feeds.bloomberg.com/markets/news.rss', 'major-financial'),
    feed('Financial Times', 'Macro', 'https://www.ft.com/?format=rss', 'major-financial'),
    feed('Wall Street Journal', 'Equities', 'https://feeds.a.dj.com/rss/RSSMarketsMain.xml', 'major-financial'),
    feed('MarketWatch', 'Equities', 'https://feeds.marketwatch.com/marketwatch/topstories/', 'major-financial'),
    feed('Yahoo Finance', 'Equities', 'https://finance.yahoo.com/news/rssindex', 'major-financial'),
    feed('Business Insider', 'Equities', 'https://www.businessinsider.com/rss', 'major-financial'),
    feed('Forbes', 'Equities', 'https://www.forbes.com/business/feed/', 'major-financial'),
    feed('Fortune', 'Equities', 'https://fortune.com/feed/fortune-feeds/', 'major-financial', False, 'Public endpoint currently returns a webpage rather than RSS; no scraping workaround used.'),
    feed('Investopedia', 'Macro', 'https://www.investopedia.com/feedbuilder/feed/getfeed?feedName=rss_articles', 'major-financial', False, 'Public feed currently blocks automated access; no bypass attempted.'),
    feed('Nasdaq', 'Equities', 'https://www.nasdaq.com/feed/rssoutbound?category=Markets', 'major-financial'),
    feed('BBC Business', 'Macro', 'https://feeds.bbci.co.uk/news/business/rss.xml', 'major-financial'),
    # Tier 3: specialist and discovery leads; never sufficient alone for a hard fact
    feed('Investing.com Markets', 'Macro', 'https://www.investing.com/rss/news_25.rss', 'specialist'),
    feed('Investing.com Commodities', 'Commodities', 'https://www.investing.com/rss/news_14.rss', 'specialist'),
    feed('Investing.com Economy', 'Macro', 'https://www.investing.com/rss/news_301.rss', 'specialist'),
    feed('Seeking Alpha', 'Equities', 'https://seekingalpha.com/feed.xml', 'specialist'),
    feed('Benzinga', 'Equities', 'https://www.benzinga.com/feed', 'specialist'),
    feed('CoinDesk', 'Crypto', 'https://www.coindesk.com/arc/outboundfeeds/rss/', 'specialist'),
    feed('Cointelegraph', 'Crypto', 'https://cointelegraph.com/rss', 'specialist'),
    feed('Cboe', 'Equities', 'https://www.cboe.com/rss/news/', 'specialist', False, 'Cboe does not expose a verified general-news RSS endpoint; no paid news API used.'),
    feed('Barrons', 'Equities', 'https://feeds.a.dj.com/rss/RSSBarrons.xml', 'specialist', False, 'Public feed currently returns 403; no bypass attempted.'),
    feed('Investor’s Business Daily', 'Equities', 'https://www.investors.com/feed/', 'specialist'),
    feed('OilPrice', 'Commodities', 'https://oilprice.com/rss/main', 'specialist'),
    feed('Eulerpool', 'Macro', 'https://eulerpool.com/en/rss', 'specialist', False, 'Public RSS endpoint returned 404 during audit; no API key or scrape workaround used.'),
    feed('USGS Earthquakes', 'Natural events', 'https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.atom', 'discovery'),
]
DISCOVERY = [
    ('Public news discovery: geopolitics', 'Geopolitics', 'geopolitics OR conflict OR war'),
    ('Public news discovery: trade', 'Geopolitics', 'tariff OR sanctions OR trade restriction'),
    ('Public news discovery: supply', 'Commodities', 'oil OR gas OR OPEC OR supply disruption'),
]
state = {'items': [], 'last_refresh': None, 'source_health': {}, 'errors': [], 'refreshing': False}
lock = threading.Lock()

def now():
    return datetime.now(timezone.utc).isoformat()

def clean(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', value or ''))).strip()

def domain(url):
    try:
        host = urlsplit(url or '').netloc.lower()
        return re.sub(r'^www\.', '', host) or 'unknown'
    except Exception:
        return 'unknown'

def canonical_url(url):
    try:
        p = urlsplit(url or '')
        keep = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith(('utm_', 'ref', 'output'))]
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/'), urlencode(keep), ''))
    except Exception:
        return url or ''

def parsed_date(value, fallback=None):
    raw = (value or '').strip()
    if raw:
        try:
            d = parsedate_to_datetime(raw)
        except Exception:
            try:
                d = datetime.fromisoformat(raw.replace('Z', '+00:00'))
            except Exception:
                d = None
        if d:
            d = d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
            return d.isoformat(), 'published'
    return (fallback or now()), 'retrieved'

def child(element, names):
    wanted = {n.lower() for n in names}
    for c in list(element):
        if c.tag.split('}')[-1].lower() in wanted:
            return ''.join(c.itertext()).strip()
    return ''

def parse(raw, spec, fallback):
    text = raw.decode('utf-8', errors='replace') if isinstance(raw, (bytes, bytearray)) else str(raw)
    root = ET.fromstring(XML_INVALID.sub('', text))
    output = []
    nodes = [e for e in root.iter() if e.tag.split('}')[-1].lower() in ('item', 'entry')][:MAX_PER_SOURCE]
    for node in nodes:
        title = clean(child(node, {'title'}))
        link = child(node, {'link'})
        for c in list(node):
            if c.tag.split('}')[-1].lower() == 'link' and c.attrib.get('href'):
                link = c.attrib['href']
                break
        if not title:
            continue
        excerpt = clean(child(node, {'description', 'summary', 'content', 'encoded'}))[:700]
        published, stamp_type = parsed_date(child(node, {'pubdate', 'published', 'updated', 'date'}))
        url = link or fallback
        tier = spec['tier']
        base = analyse(title, excerpt, spec['category'], tier)
        source_record = {'name': spec['name'], 'domain': domain(url), 'url': url, 'title': title, 'published': published, 'timestamp_type': stamp_type, 'tier': tier, 'excerpt': excerpt, 'source_family': spec['name'].lower()}
        output.append({
            'id': hashlib.sha1((title + canonical_url(url)).encode()).hexdigest()[:16],
            'title': title, 'summary': base['summary'], 'excerpt': excerpt, 'url': url,
            'source': spec['name'], 'domain': domain(url), 'category': spec['category'],
            'published': published, 'timestamp_type': stamp_type, 'source_tier': tier,
            'score': base['score'], 'score_breakdown': base.get('score_breakdown', {}),
            'reasons': base['reasons'], 'market_relevance': base['market_relevance'],
            'analysis_provider': base['analysis_provider'], 'affected_assets': base.get('affected_assets', []),
            'confidence': base.get('confidence', 'low'), 'why_it_matters': base.get('why_it_matters', base['market_relevance']),
            'sources': [source_record], 'verification': 'single-source', 'corroboration': 1,
            'connections': [], 'event_status': 'unverified', 'speculation': 'Market transmission is analytical, not confirmed causation.'
        })
    return output

def fetch(url):
    request = Request(url, headers={'User-Agent': 'SignalWire/3.0 (+public research dashboard)', 'Accept': 'application/rss+xml,application/atom+xml,application/xml,text/xml'})
    with urlopen(request, timeout=TIMEOUT) as response:
        return response.read()

def fetch_one(spec):
    try:
        items = parse(fetch(spec['url']), spec, spec['url'])
        return spec['name'], items, {'ok': True, 'count': len(items), 'url': spec['url'], 'tier': spec['tier'], 'access': spec['access']}, None
    except Exception as exc:
        return spec['name'], [], {'ok': False, 'count': 0, 'url': spec['url'], 'tier': spec['tier'], 'access': spec['access'], 'error': str(exc)[:180]}, f"{spec['name']}: {str(exc)[:140]}"

def distinct_sources(group):
    seen_urls = set(); rows = []
    for source in group.get('sources', []):
        key = canonical_url(source.get('url', ''))
        if key and key in seen_urls:
            continue
        seen_urls.add(key); rows.append(source)
    return rows

WIRE_ORIGINS = {
    'reuters': re.compile(r'\\breuters\\b', re.I),
    'associated press': re.compile(r'\\b(associated press|the ap|ap news)\\b', re.I),
    'bloomberg': re.compile(r'\\bbloomberg\\b', re.I),
}
def underlying_family(source):
    """Estimate the information chain so syndicated copy is not counted twice.
    This is deliberately conservative: it collapses only explicit wire/origin
    references and otherwise keeps the publisher as an independent family.
    """
    text = ' '.join(str(source.get(k, '')) for k in ('title', 'excerpt', 'url')).lower()
    for origin, pattern in WIRE_ORIGINS.items():
        if pattern.search(text):
            return origin
    return str(source.get('source_family') or source.get('name') or source.get('domain') or 'unknown').lower()
def independent_count(sources):
    return len({underlying_family(s) for s in sources if underlying_family(s) not in ('', 'unknown')})

def merge(items):
    groups = []
    # Official feeds are placed first so their titles/claims anchor a cluster.
    ordered = sorted(items, key=lambda x: ({'official': 0, 'major-financial': 1, 'specialist': 2, 'discovery': 3}.get(x.get('source_tier'), 4), x.get('published', '')))
    for current in ordered:
        match = next((g for g in groups if similar(g.get('title', ''), current.get('title', ''))), None)
        if not match:
            groups.append(current)
            continue
        match['sources'] = distinct_sources(match)
        existing_urls = {canonical_url(s.get('url', '')) for s in match['sources']}
        for source in current.get('sources', []):
            if canonical_url(source.get('url', '')) not in existing_urls:
                match['sources'].append(source); existing_urls.add(canonical_url(source.get('url', '')))
        match['sources'] = distinct_sources(match)
        # Prefer the strongest evidence record for the event summary and URL.
        if current.get('source_tier') == 'official' and match.get('source_tier') != 'official':
            for key in ('title', 'summary', 'excerpt', 'url', 'source', 'domain', 'published', 'timestamp_type'):
                match[key] = current.get(key, match.get(key))
            match['score_breakdown'] = current.get('score_breakdown', match.get('score_breakdown', {}))
        match['source_tier'] = max((s.get('tier', 'discovery') for s in match['sources']), key=lambda z: ['discovery', 'specialist', 'major-financial', 'official'].index(z))
        match['corroboration'] = independent_count(match['sources'])
        match['independent_domains'] = len({s.get('domain') for s in match['sources'] if s.get('domain') not in ('', 'unknown')})
        match['score'] = min(100, int(match.get('score', 0)) + min(16, 5 * max(0, match['corroboration'] - 1)))
        match['reasons'] = list(dict.fromkeys(match.get('reasons', []) + ['cross-source support']))[:8]

    out = []
    for event in groups:
        sources = distinct_sources(event)
        official = [s for s in sources if s.get('tier') == 'official']
        domains = {s.get('domain') for s in sources if s.get('domain') not in ('', 'unknown')}
        independent = independent_count(sources)
        event['sources'] = sources
        event['corroboration'] = independent
        event['independent_domains'] = len(domains)
        event['source_count'] = len(sources)
        event['verification'] = 'confirmed' if official else 'verified' if independent >= 2 else 'single-source'
        event['event_status'] = 'confirmed' if official else 'corroborated' if independent >= 2 else 'developing' if event.get('source_tier') in ('major-financial', 'specialist') else 'unverified'
        event['verification_label'] = 'Confirmed official data' if official else 'Corroborated across 2+ independent information chains' if independent >= 2 else 'Reported lead — verify carefully'
        event['confidence'] = 'high' if official and independent >= 2 else 'medium' if official or independent >= 2 else 'low'
        text = (event.get('title', '') + ' ' + event.get('summary', '')).lower()
        links = []
        if any(k in text for k in ('rate', 'central bank', 'inflation', 'cpi', 'jobs', 'payroll', 'yield')): links += ['policy/growth → bonds', 'policy expectations → currencies']
        if any(k in text for k in ('oil', 'gas', 'opec', 'supply', 'shipping', 'energy')): links += ['supply → inflation expectations', 'energy → producers and transport']
        if any(k in text for k in ('tariff', 'sanction', 'trade', 'export', 'import')): links += ['trade → exporters and currencies', 'trade → supply chains']
        if any(k in text for k in ('bank', 'credit', 'default', 'loan')): links += ['credit conditions → banks', 'credit conditions → cyclical equities']
        if any(k in text for k in ('chip', 'semiconductor', 'technology')): links += ['component supply → technology and manufacturing']
        event['connections'] = list(dict.fromkeys(links))[:4]
        event['market_relevance'] = relevance_for_score(int(event.get('score', 0)))
        event['why_it_matters'] = why_it_matters_for(text, int(event.get('score', 0)))
        event['level'] = 'High' if event.get('score', 0) >= 65 else 'Medium' if event.get('score', 0) >= RELEVANCE_THRESHOLD else 'Low'
        event['freshness'] = freshness(event.get('published'))
        event['confirmed_facts'] = event.get('summary', '')
        event['speculation'] = 'The market paths listed are plausible analysis, not proof that one event caused a price move.'
        if event.get('score', 0) >= RELEVANCE_THRESHOLD:
            out.append(event)
    return sorted(out, key=lambda x: (x.get('score', 0), x.get('published', '')), reverse=True)[:250]

def freshness(value):
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(str(value).replace('Z', '+00:00'))).total_seconds()
        if age < 6 * 3600: return 'New / developing'
        if age < 48 * 3600: return 'Recent'
        return 'Older context'
    except Exception:
        return 'Timestamp uncertain'

def fetch_all():
    sources = [s for s in SOURCES if s.get('enabled', True)] + [feed(n, c, 'https://news.google.com/rss/search?q=' + quote_plus(q) + '&hl=en-US&gl=US&ceid=US:en', 'discovery') for n, c, q in DISCOVERY]
    items, health, errors = [], {}, []
    for spec in SOURCES:
        if not spec.get('enabled', True):
            health[spec['name']] = {'ok': False, 'skipped': True, 'count': 0, 'url': spec['url'], 'tier': spec['tier'], 'access': spec['access'], 'error': spec.get('note', 'Disabled until a public feed is verified.')}
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(fetch_one, spec) for spec in sources]
        for future in as_completed(futures):
            name, got, status, error = future.result()
            items.extend(got); health[name] = status
            if error: errors.append(error)
    return merge(items), health, sorted(errors)

def build_knowledge(items, previous=None):
    if isinstance(previous, dict): previous = previous.get('entries', [])
    learned = {}
    for row in previous or []:
        if not isinstance(row, dict):
            continue
        status = str(row.get('verification', '')).lower()
        # Do not carry forward legacy or downgraded claims into persistent memory.
        # Only explicit confirmation/corroboration survives a refresh.
        admitted = ('confirmed' in status or 'corroborated' in status or '2+ source' in status) and 'unverified' not in status
        if admitted and row.get('evidence_urls'):
            learned[row.get('key') or hashlib.sha1(str(row).encode()).hexdigest()[:14]] = row
    for event in items:
        if event.get('score', 0) < 45 or event.get('verification') not in ('confirmed', 'verified'):
            continue
        key = hashlib.sha1((event.get('category', '') + '|' + event_key(event.get('title', ''))).encode()).hexdigest()[:14]
        record = learned.get(key, {'key': key, 'first_seen': event.get('published'), 'observations': 0})
        record.update({'topic': event.get('title'), 'category': event.get('category'), 'last_seen': event.get('published'), 'confidence': event.get('confidence'), 'verification': event.get('verification_label'), 'source_tier': event.get('source_tier'), 'market_links': event.get('connections', []), 'evidence_urls': [s.get('url') for s in event.get('sources', [])[:4]], 'status': 'current'})
        record['observations'] = int(record.get('observations', 0)) + 1
        learned[key] = record
    return {'version': 2, 'updated': now(), 'entries': list(learned.values())[-500:]}

def save(payload):
    os.makedirs(DATA, exist_ok=True)
    tmp = CACHE + '.tmp'
    with open(tmp, 'w', encoding='utf8') as handle: json.dump(payload, handle, ensure_ascii=False)
    os.replace(tmp, CACHE)
    try:
        with open(KNOWLEDGE, encoding='utf8') as handle: previous = json.load(handle)
    except Exception:
        previous = {}
    ktmp = KNOWLEDGE + '.tmp'
    with open(ktmp, 'w', encoding='utf8') as handle: json.dump(build_knowledge(payload.get('items', []), previous), handle, ensure_ascii=False)
    os.replace(ktmp, KNOWLEDGE)

def refresh(force=False):
    with lock:
        if state['refreshing']: return False
        state['refreshing'] = True
    try:
        items, health, errors = fetch_all()
        payload = {'items': items, 'last_refresh': now(), 'source_health': health, 'errors': errors}
        save(payload)
        try:
            with open(KNOWLEDGE, encoding='utf8') as handle: payload['knowledge'] = json.load(handle)
        except Exception:
            payload['knowledge'] = {'version': 2, 'entries': []}
        with lock: state.update(payload)
    finally:
        with lock: state['refreshing'] = False
    return True

def init():
    try:
        with open(CACHE, encoding='utf8') as handle: state.update(json.load(handle))
    except Exception:
        pass
    if not state['items']:
        threading.Thread(target=refresh, daemon=True).start()

if HAS_FLASK:
    app = Flask(__name__)
    @app.get('/')
    def index(): return render_template('index.html')
    @app.get('/api/items')
    def api(): return jsonify(state)
    @app.post('/api/refresh')
    def api_refresh(): threading.Thread(target=refresh, args=(True,), daemon=True).start(); return jsonify({'accepted': True})
    @app.get('/api/knowledge')
    def knowledge():
        try:
            with open(KNOWLEDGE, encoding='utf8') as handle: return jsonify(json.load(handle))
        except Exception: return jsonify({'version': 2, 'entries': []})
    @app.get('/health')
    def health(): return jsonify({'ok': True, 'items': len(state['items']), 'last_refresh': state['last_refresh']})

if __name__ == '__main__':
    init(); app.run(host='0.0.0.0', port=PORT, debug=False)
