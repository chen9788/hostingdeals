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
        if item.get('withdraw_at') and now >= dt.datetime.fromisoformat(item['withdraw_at']): return False
        if item.get('source_start_date') and now.date() < dt.date.fromisoformat(item['source_start_date']): return False
        return True
    except (ValueError, KeyError, TypeError):
        return False

def parse(brand, text, url, now, diagnostics=None):
    """Fail closed: each recipe requires an explicit code/discount association."""
    if not official(brand, url): return []
    if re.search(r'just a moment|verify you are human|access denied|captcha', text, re.I): return []
    compact = ' '.join(text.split())
    offers = []
    if brand == 'godaddy':
        # With no reviewed readable card layout, only a self-contained official
        # instruction can qualify. A percentage elsewhere on the page is insufficient.
        pattern = (r'(?m)^(?i:Use|Apply) (?i:(?:coupon |promo )?code):? +'
                   r'(?P<code>[A-Z0-9_-]{3,40}) (?i:for|to get) '
                   r'(?P<discount>\d+%(?i: off| discount))(?P<scope>[^\n]{0,120})$')
        for m in re.finditer(pattern, text):
            if re.search(r'expired|no longer|ended|expires|until|valid through', m.group(0), re.I): continue
            offers.append({'brand': brand, 'code': m['code'], 'discount': m['discount'],
                'terms': m['scope'].strip() or 'Product/account eligibility not verified; check official terms.',
                'valid_until': None, 'expiry_note': 'not verified — no fixed deadline captured',
                'source_url': url, 'checked_at': now, 'status': 'officially_observed',
                'checkout_status': 'not verified', 'evidence': m.group(0)})
        return offers
    if brand == 'namecheap':
        dates = re.search(r'Valid ([A-Za-z]+ \d+) - ([A-Za-z]+ \d+, \d{4})', compact)
        restriction = 'Promotional price applies to first-year registrations and transfers only and is not applicable for premium or aftermarket domains.'
        if not dates or restriction not in compact: return []
        try:
            end = dt.datetime.strptime(dates[2], '%B %d, %Y').date()
            start = dt.datetime.strptime(dates[1] + ', ' + str(end.year), '%B %d, %Y').date()
        except ValueError: return []
        recipes = [
            ('Domain registration / transfer', r'(Discounted registration and transfer)\nSee details below\n([A-Z0-9_-]{3,40})\nRegister domain', restriction + ' Prices vary by TLD; see the official table.'),
            ('Professional Business Email', r'(Up to \d+% off all plans - Professional Business Email)\nSee details below\n([A-Z0-9_-]{3,40})\nGet email', 'Discount varies by plan and billing period; see the official table.'),
            ('Standard Wildcard SSL', r'(Up to \d+% off Standard Wildcard SSL - SSL Security)\nSee details below\n([A-Z0-9_-]{3,40})\nSecure your site', 'Price varies by certificate duration; see the official table.')]
        for product, pattern, terms in recipes:
            m = re.search(pattern, text)
            if not m: continue
            offers.append({'brand': brand, 'product': product, 'code': m[2], 'discount': m[1],
                'terms': terms, 'source_start_date': start.isoformat(), 'source_end_date': end.isoformat(),
                'valid_until': None,
                'withdraw_at': dt.datetime.combine(end, dt.time(), tzinfo=dt.timezone.utc).isoformat(),
                'expiry_note': dates.group(0) + '; timezone not verified. Conservatively removed at 00:00 UTC on the listed end date; while supplies last.',
                'source_url': url, 'checked_at': now, 'status': 'officially_observed',
                'checkout_status': 'not verified', 'evidence': ' / '.join([m[1], m[2], dates.group(0)])})
        return offers
    if brand == 'hostinger':
        # Match a single rendered plan block, so a headline discount cannot be
        # misrepresented as the incremental saving from entering a coupon.
        plan_pattern = (r'(?P<discount>\d+% off)\s*\n(?P<product>Premium|Unlimited|Cloud Startup)\n'
                        r'(?:(?!\n(?:Premium|Unlimited|Cloud Startup)\n).){0,450}?'
                        r"'(?P<code>COUPONSPAGE)' coupon applied\s*\nUse coupon\s*\n"
                        r'(?P<terms>(?:Get \d+ months for|Today you pay)[^\n]+)')
        for m in re.finditer(plan_pattern, text, re.S):
            offers.append({'brand': brand, 'code': m['code'], 'product': m['product'],
                'discount': m['discount'] + ' — displayed plan discount, not incremental code savings',
                'terms': m['terms'], 'valid_until': None,
                'expiry_note': 'not verified — no fixed deadline captured',
                'source_url': url, 'checked_at': now, 'status': 'officially_observed',
                'checkout_status': 'not verified',
                'evidence': m['discount'] + ' / ' + m['product'] + " / 'COUPONSPAGE' coupon applied / " + m['terms']})
        if diagnostics is not None:
            candidate_pattern = (
                r'\d+% off\s*\n(?:Premium|Unlimited|Cloud Startup)\n'
                r'(?:(?!\n(?:Premium|Unlimited|Cloud Startup)\n).){0,450}?'
                r"'COUPONSPAGE' coupon applied")
            candidates = list(re.finditer(candidate_pattern, text, re.S))
            diagnostics['candidates_detected'] = len(candidates)
            diagnostics['primary_matched'] = len(offers)
            diagnostics['suspected_copy_change'] = bool(candidates and not offers)
        if offers: return offers
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
                       dt.datetime.fromisoformat(until) if until else dt.datetime.max.replace(tzinfo=dt.timezone.utc),
                       dt.datetime.fromisoformat(item['withdraw_at']) if item.get('withdraw_at') else dt.datetime.max.replace(tzinfo=dt.timezone.utc))
        cards.append('<article class="notice dynamic-offer" data-hide-at="' + esc(deadline.isoformat()) + '">'
            '<h3><code>' + esc(item['code']) + '</code>' + (' · ' + esc(item['product']) if item.get('product') else '') + '</h3>'
            '<p>' + esc(item['discount']) + '</p>'
            + ('<p>' + esc(item['terms']) + '</p>' if item.get('terms') else '') +
            '<p>Officially published; checkout eligibility: <strong>not verified</strong>.</p>'
            '<p>Validity: ' + esc(item.get('expiry_note') or until or 'not verified') + '</p>'
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
