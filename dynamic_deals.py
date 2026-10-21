"""Brand-only official coupon layer; unknown redemption is never called active."""
import datetime as dt
import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
DOMAINS = {'hostinger': 'hostinger.com', 'namecheap': 'namecheap.com', 'godaddy': 'godaddy.com'}

def official(brand, url):
    u = urlsplit(url)
    return (u.scheme == 'https' and not u.username and not u.password
            and (u.hostname == DOMAINS[brand] or (u.hostname or '').endswith('.' + DOMAINS[brand])))

def current(item, now):
    try:
        checked = dt.datetime.fromisoformat(item['checked_at'])
        if checked.tzinfo is None or not dt.timedelta(0) <= now - checked <= dt.timedelta(hours=48): return False
        if not official(item['brand'], item['source_url']): return False
        if item.get('status') != 'officially_observed': return False
        if not re.fullmatch(r'[A-Z0-9_-]{3,40}', item['code']): return False
        if item.get('valid_until') and now >= dt.datetime.fromisoformat(item['valid_until']): return False
        return True
    except (ValueError, KeyError, TypeError):
        return False

def parse(brand, text, url, now):
    """Fail closed: each recipe requires an explicit code/discount association."""
    if not official(brand, url): return []
    if re.search(r'just a moment|verify you are human|access denied|captcha', text, re.I): return []
    compact = ' '.join(text.split())
    offers = []
    if brand == 'hostinger':
        # Deliberately tied to the official coupon instruction, not arbitrary uppercase words.
        patterns = [r'(?:coupon code|code)\s*[:\-]?\s*(?P<code>COUPONSPAGE)\b.{0,180}?(?P<discount>\d+%\s*(?:off|discount))',
                    r'(?P<discount>\d+%\s*(?:off|discount)).{0,180}?(?:coupon code|code)\s*[:\-]?\s*(?P<code>COUPONSPAGE)\b']
        for pattern in patterns:
            m = re.search(pattern, compact, re.I)
            if m:
                offers.append({'brand': brand, 'code': m['code'].upper(), 'discount': m['discount'],
                    'valid_until': None, 'expiry_note': 'not verified — no fixed deadline captured',
                    'source_url': url, 'checked_at': now, 'status': 'officially_observed',
                    'checkout_status': 'not verified', 'evidence': m.group(0)})
                break
    return offers

def render(brand, now):
    config = json.loads((ROOT / 'config/dynamic-deals.json').read_text(encoding='utf-8'))
    if brand not in config['enabled']: return ''
    path = ROOT / 'data/dynamic-deals.json'
    data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    state = data.get('sources', {}).get(brand, {})
    esc = lambda s: html.escape(str(s), quote=True)
    cards = []
    for item in data.get('offers', []):
        if item.get('brand') != brand or not current(item, now): continue
        until = item.get('valid_until')
        deadline = min(dt.datetime.fromisoformat(item['checked_at']) + dt.timedelta(hours=48),
                       dt.datetime.fromisoformat(until) if until else dt.datetime.max.replace(tzinfo=dt.timezone.utc))
        cards.append('<article class="notice dynamic-offer" data-hide-at="' + esc(deadline.isoformat()) + '">'
            '<h3><code>' + esc(item['code']) + '</code> · ' + esc(item['discount']) + '</h3>'
            '<p>Officially published; checkout eligibility: <strong>not verified</strong>.</p>'
            '<p>Valid until: ' + esc(until or item['expiry_note']) + '</p>'
            '<p>Official check: <time>' + esc(item['checked_at']) + '</time> · '
            '<a href="' + esc(item['source_url']) + '" rel="noopener noreferrer">Official source</a></p></article>')
    return ('<section class="prose" id="current-deals"><p class="eyebrow">OFFICIAL SOURCE MONITOR</p>'
        '<h2>Latest qualifying deals</h2><p>Official publication and checkout tests are separate. '
        'This layer refreshes daily; records leave this list after a captured deadline or 48 hours without a fresh check. '
        'Removal does not establish permanent invalidity. Unknown expiry stays not verified.</p>'
        + ''.join(cards) + '<p class="dynamic-empty"' + (' hidden' if cards else '') + '>'
        'Current coupon availability: <strong>not verified</strong>. No freshly qualifying code in this layer.</p>'
        '<p>Last attempt: ' + esc(state.get('checked_at', 'not yet run')) + ' · Source status: '
        + esc(state.get('status', 'not verified')) + ' · <a href="' + esc(config['sources'][brand])
        + '" rel="noopener noreferrer">Check official promotions</a> · <a href="/data/dynamic-deals.json">Monitor evidence</a></p>'
        '<script src="/assets/dynamic-deals.js" defer></script></section>')
