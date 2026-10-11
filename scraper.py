"""Official-source offer monitor. Python standard library only; never runs JS or AI."""
from __future__ import annotations
import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UA = 'hostingdeals/1.0 (official-offer-monitor; daily; no-login)'
MAX_BYTES = 3_000_000

class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.links, self.feeds = [], [], []
        self.skip = 0
        self.anchor = None
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style', 'noscript', 'template'): self.skip += 1
        if tag == 'a': self.anchor = [a.get('href', ''), []]
        if tag == 'link' and a.get('type') in ('application/rss+xml','application/atom+xml'):
            self.feeds.append(a.get('href', ''))
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'template'): self.skip = max(0, self.skip - 1)
        if tag == 'a' and self.anchor:
            self.links.append((self.anchor[0], ' '.join(self.anchor[1])))
            self.anchor = None
    def handle_data(self, data):
        text = ' '.join(data.split())
        if text and not self.skip:
            self.parts.append(text)
            if self.anchor: self.anchor[1].append(text)
    @property
    def text(self): return ' '.join(self.parts)

def official(url, domains):
    p = urllib.parse.urlsplit(url)
    return p.scheme == 'https' and not p.username and not p.password and any(
        p.hostname == d or (p.hostname or '').endswith('.' + d) for d in domains)

class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, domains): self.domains = domains
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not official(newurl, self.domains): raise ValueError('Redirect outside official allowlist')
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def fetch(url, domains):
    """Validate TLS and every redirect. No anti-bot or security bypasses."""
    if not official(url, domains): raise ValueError('Source outside official allowlist')
    opener = urllib.request.build_opener(OfficialRedirect(domains))
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA,
                'Accept-Language': 'en-US,en;q=0.8', 'Accept': 'text/html,application/xml,text/plain'})
            with opener.open(req, timeout=15) as response:
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES: raise ValueError('Source exceeds size limit')
                charset = response.headers.get_content_charset() or 'utf-8'
                return {'url': response.url, 'status': response.status,
                    'body': raw.decode(charset, errors='strict'),
                    'sha256': hashlib.sha256(raw).hexdigest()}
        except urllib.error.HTTPError as exc:
            if exc.code not in (500, 502, 503, 504) or attempt: raise
        except (TimeoutError, urllib.error.URLError):
            if attempt: raise
        time.sleep(1)
    raise RuntimeError('Fetch exhausted')

def extract(provider, body, final_url, now):
    page = Page(); page.feed(body)
    if re.search(r'captcha|verify you are human|access denied|just a moment', page.text, re.I):
        return [], 'blocked'
    if any(marker in final_url for marker in provider.get('reject_url_markers', [])):
        return [], 'region_mismatch'
    offers = []
    for recipe in provider.get('recipes', []):
        m = re.search(recipe['pattern'], page.text, re.I)
        if not m: continue
        groups = {k: ' '.join(v.split()) for k, v in m.groupdict().items() if v is not None}
        for field, pattern in recipe.get('field_patterns', {}).items():
            field_match = re.search(pattern, page.text, re.I)
            if field_match: groups[field] = field_match.group(0)
        # Supporting restrictions must also remain in the source, or suppress the offer.
        terms = []
        for pattern in recipe.get('terms_patterns', []):
            t = re.search(pattern, page.text, re.I)
            if not t: break
            terms.append(t.group(0))
        else:
            valid_from, valid_until = groups.get('valid_from'), groups.get('valid_until')
            if valid_until:
                try:
                    end = dt.datetime.strptime(valid_until, '%B %d, %Y').date()
                    start = dt.datetime.strptime(valid_from + f', {end.year}', '%B %d, %Y').date() if valid_from else None
                    valid_until = end.isoformat(); valid_from = start.isoformat() if start else None
                except ValueError:
                    # Unknown date syntax is suppressed rather than assumed current.
                    continue
            offers.append({'id': provider['id'] + '-' + recipe['id'], 'provider': provider['id'],
                'title': recipe['title'], 'category': provider['category'], 'status': 'observed',
                'source_url': final_url, 'offer_url': final_url, 'price_text': groups.get('price'),
                'renewal_text': groups.get('renewal'), 'discount_text': groups.get('discount'),
                'benefit_text': groups.get('benefit'), 'term_text': groups.get('term'),
                'eligibility_text': groups.get('eligible'),
                'code': groups.get('code'), 'valid_from': valid_from,
                'valid_until': valid_until, 'currency': groups.get('currency'),
                'checked_at': now, 'first_seen_at': now, 'evidence': m.group(0)[:350],
                'terms_evidence': terms, 'checkout_tested': False,
                'source_sha256': hashlib.sha256(body.encode('utf-8')).hexdigest()})
    return offers, ('ok' if offers else 'no_extractable_offer')

def collect(provider, now):
    domains = provider['domains']
    state = {'id': provider['id'], 'checked_at': now, 'offers': 0, 'status': 'unavailable',
        'sitemaps': [], 'feeds': [], 'candidates': [], 'errors': [], 'js_mode': 'unknown'}
    robots_cache = {}
    def permitted(url):
        parsed = urllib.parse.urlsplit(url)
        origin = parsed.scheme + '://' + parsed.netloc
        if origin not in robots_cache:
            try:
                r = fetch(origin + '/robots.txt', domains)
                robot = urllib.robotparser.RobotFileParser(); robot.parse(r['body'].splitlines())
                robots_cache[origin] = robot
                state['sitemaps'].extend(re.findall(r'^Sitemap:\s*(\S+)', r['body'], re.M | re.I))
                delay = robot.crawl_delay(UA) or robot.crawl_delay('*') or 0
                robots_cache[origin + ':delay'] = min(delay, 30)
            except urllib.error.HTTPError as exc:
                if exc.code == 404: robots_cache[origin] = None
                else: robots_cache[origin] = False; state['errors'].append(f'robots: HTTP {exc.code}')
            except Exception as exc:
                robots_cache[origin] = False; state['errors'].append(f'robots: {type(exc).__name__}: {exc}')
        robot = robots_cache[origin]
        if robot is False: return False
        if robot and not robot.can_fetch(UA, url): return False
        time.sleep(max(0.15, robots_cache.get(origin + ':delay', 0)))
        return True
    # Inspect home navigation and advertised RSS/Atom entries; do not follow third-party links.
    try:
        if permitted(provider['home']):
            h = fetch(provider['home'], domains); p = Page(); p.feed(h['body'])
            state['home_url'] = h['url']; state['home_status'] = h['status']
            state['feeds'] = sorted(set(urllib.parse.urljoin(h['url'], u) for u in p.feeds
                if official(urllib.parse.urljoin(h['url'], u), domains)))
            state['candidates'] = sorted(set(urllib.parse.urljoin(h['url'], u) for u, label in p.links
                if re.search(r'promo|coupon|deal|pricing|special', u + ' ' + label, re.I)
                and official(urllib.parse.urljoin(h['url'], u), domains)))[:30]
    except Exception as exc: state['errors'].append(f'home: {type(exc).__name__}: {exc}')
    offers = []
    for url in provider['offer_sources']:
        try:
            if not permitted(url):
                state['status'] = 'robots_unavailable_or_disallowed'; continue
            source = fetch(url, domains)
            found, status = extract(provider, source['body'], source['url'], now)
            state['source_url'] = source['url']; state['http_status'] = source['status']
            state['status'] = status
            if found: state['js_mode'] = 'not_required_for_extracted_fields'
            elif status == 'no_extractable_offer': state['js_mode'] = 'unknown_or_markup_changed'
            offers.extend(found)
        except Exception as exc:
            state['errors'].append(f'offer: {type(exc).__name__}: {exc}')
    state['sitemaps'] = sorted(set(u for u in state['sitemaps'] if official(u, domains)))
    # One advertised sitemap/feed can discover candidates; unknown pages are never auto-published.
    for url in (state['sitemaps'][:1] + state['feeds'][:1]):
        try:
            if not permitted(url): continue
            r = fetch(url, domains); xml = ET.fromstring(r['body'])
            urls = [n.text for n in xml.iter() if n.tag.split('}')[-1] in ('loc','link') and n.text]
            state['candidates'] = sorted(set(state['candidates'] + [u for u in urls
                if official(u, domains) and re.search(r'promo|coupon|deal|special', u, re.I)]))[:30]
        except Exception as exc: state['errors'].append(f'discovery: {type(exc).__name__}: {exc}')
    state['offers'] = len(offers)
    if offers: state['status'] = 'ok'
    return offers, state

def save_atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    tmp.replace(path)

def refresh(root=ROOT):
    providers = json.loads((root / 'config/providers.json').read_text(encoding='utf-8'))
    path = root / 'data/offers.json'
    old = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'offers': []}
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    previous = {o['id']: o for o in old['offers']}
    offers, states = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for found, state in pool.map(lambda p: collect(p, now), providers):
            states.append(state)
            for offer in found:
                prior = previous.get(offer['id'])
                if prior: offer['first_seen_at'] = prior['first_seen_at']
                offers.append(offer)
    seen = {o['id'] for o in offers}
    for prior in old['offers']:
        if prior['id'] not in seen:
            offers.append({**prior, 'status': 'unavailable', 'last_attempt_at': now})
    save_atomic(path, {'schema_version': 1, 'generated_at': now, 'locale': 'en-US',
        'offers': sorted(offers, key=lambda o: o['id']), 'sources': states})
    history_path = root / 'data/history.json'
    history = json.loads(history_path.read_text(encoding='utf-8')) if history_path.exists() else []
    keys = ['status','price_text','renewal_text','discount_text','benefit_text','term_text','code','valid_from','valid_until']
    for offer in offers:
        before = {k: previous[offer['id']].get(k) for k in keys} if offer['id'] in previous else None
        after = {k: offer.get(k) for k in keys}
        if before != after:
            history.append({'observed_at': now, 'offer_id': offer['id'], 'title': offer['title'],
                'before': before, 'after': after, 'source_url': offer['source_url']})
    save_atomic(history_path, history[-2000:])
    summary = {'generated_at': now, 'observed_offers': len(seen),
        'provider_status': {s['id']: s['status'] for s in states}}
    save_atomic(root / 'data/health.json', summary)
    print(json.dumps(summary, indent=2))
    return summary

if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    refresh()
