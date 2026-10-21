"""Scheduled, signed-out, HEADED Google Chrome. Never falls back to headless/HTTP."""
import datetime as dt
import hashlib
import json
import re
import urllib.robotparser
from pathlib import Path
from playwright.sync_api import sync_playwright
from dynamic_deals import ROOT, official, parse

def main():
    config = json.loads((ROOT / 'config/dynamic-deals.json').read_text())
    evidence = ROOT / 'work/dynamic-evidence'
    evidence.mkdir(parents=True, exist_ok=True)
    result = {'schema_version': 1, 'mode': 'Google Chrome headed (Xvfb virtual display on CI)', 'requested_locale': 'en-US', 'sources': {}, 'offers': []}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=False)
        context = browser.new_context(locale='en-US', viewport={'width': 1440, 'height': 1000})
        result['browser_version'] = browser.version
        for brand in config['enabled']:
            now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
            state = {'checked_at': now, 'source_url': config['sources'][brand], 'status': 'not verified'}
            page = context.new_page()
            # Only permit official top-level destinations; no login or challenge solving.
            def route_document(route, request):
                if request.is_navigation_request() and request.frame == page.main_frame and not official(brand, request.url):
                    route.abort()
                else: route.continue_()
            page.route('**/*', route_document)
            try:
                source = config['sources'][brand]
                from urllib.parse import urlsplit
                origin = urlsplit(source)
                robots_response = page.goto(origin.scheme + '://' + origin.netloc + '/robots.txt', wait_until='domcontentloaded', timeout=30000)
                if robots_response and robots_response.status == 200:
                    robots_text = page.locator('body').inner_text()
                    robot = urllib.robotparser.RobotFileParser()
                    robot.parse(robots_text.splitlines())
                    if not robot.can_fetch('*', source):
                        raise RuntimeError('robots disallowed')
                elif not robots_response or robots_response.status != 404:
                    raise RuntimeError('robots unavailable')
                state['robots'] = 'permitted'
                response = page.goto(config['sources'][brand], wait_until='domcontentloaded', timeout=60000)
                if re.search(r'/(?:en-in|en-gb|en-au|in|uk|eu)/|https://eu\.', page.url, re.I):
                    raise RuntimeError('region-mismatch redirect; no offer published')
                page.locator('body').wait_for()
                # Await the rendered coupon instruction, but retain failures as evidence.
                try: page.get_by_text(re.compile(r'COUPONSPAGE|coupon|promo', re.I)).first.wait_for(timeout=10000)
                except Exception: pass
                text = page.locator('body').inner_text(timeout=15000)
                state.update(final_url=page.url, http_status=response.status if response else None,
                             text_sha256=hashlib.sha256(text.encode()).hexdigest())
                (evidence / (brand + '.txt')).write_text(text, encoding='utf-8')
                page.screenshot(path=str(evidence / (brand + '.png')), full_page=True)
                found = parse(brand, text, page.url, now) if response and response.status == 200 else []
                result['offers'].extend(found)
                state['status'] = 'officially_observed' if found else 'not verified — no matching official code captured'
                if response and response.status != 200:
                    state['status'] = 'not verified — official source returned HTTP ' + str(response.status)
                state['offers'] = len(found)
                print(brand, json.dumps(state))
                print('Coupon context:', '\n'.join(line for line in text.splitlines() if re.search(r'coupon|code|%|valid|expire', line, re.I))[:8000])
            except Exception as exc:
                state['status'] = 'not verified — browser fetch failed'
                state['error'] = type(exc).__name__ + ': ' + str(exc).splitlines()[0][:250]
                print(brand, json.dumps(state))
            finally:
                result['sources'][brand] = state
                page.close()
        browser.close()
    target = ROOT / 'data/dynamic-deals.json'
    tmp = target.with_suffix('.tmp')
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(target)
    (evidence / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')

if __name__ == '__main__': main()
