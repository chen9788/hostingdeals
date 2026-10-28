"""Render a static site from observed official data. No third-party dependencies."""
from __future__ import annotations
import argparse
import hashlib
import csv
import datetime as dt
import html
import io
import json
import os
import shutil
from pathlib import Path
from string import Template
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
from structured_data import render as structured_data
from dynamic_deals import render as dynamic_layer

ROOT = Path(__file__).resolve().parent
def esc(value): return html.escape(str(value or ''), quote=True)
def load(path): return json.loads((ROOT / path).read_text(encoding='utf-8'))
def template(filename, **values):
    values.setdefault("jsonld", "")
    values.setdefault("coupon_nav", "")
    values.setdefault("icon_version", hashlib.sha256((ROOT / "assets/favicon.svg").read_bytes()).hexdigest()[:12])
    values.setdefault("style_version", hashlib.sha256((ROOT / "assets/style.css").read_bytes()).hexdigest()[:12])
    return Template((ROOT / 'templates' / filename).read_text(encoding='utf-8')).substitute(values)
def fresh(offer, now):
    if offer['status'] != 'observed': return False
    checked = dt.datetime.fromisoformat(offer['checked_at'])
    if now - checked > dt.timedelta(hours=48): return False
    if offer.get('valid_from'):
        try:
            if dt.date.fromisoformat(offer['valid_from']) > now.date(): return False
        except ValueError: return False
    if offer.get('valid_until'):
        try:
            if dt.date.fromisoformat(offer['valid_until']) < now.date(): return False
        except ValueError: return False  # Unparsed validity is never treated as active.
    return True
def outbound(url, label, sponsored=False):
    if urlsplit(url).scheme != 'https': raise ValueError('Outbound URLs must be HTTPS')
    return f'<a href="{esc(url)}" rel="{("sponsored " if sponsored else "")}noopener noreferrer">{esc(label)} ↗</a>'
def target(offer, monetization):
    affiliate = monetization['affiliate_links'].get(offer['provider'])
    if affiliate and affiliate.get('approved') is True and affiliate.get('reviewed_at') and affiliate.get('program_url'):
        return affiliate['url'], True
    return offer['offer_url'], False
def card(offer, providers, monetization):
    p = providers[offer['provider']]
    value = offer.get('price_text') or offer.get('discount_text') or offer.get('benefit_text') or 'See source'
    return f'''<article class="deal-card"><div class="card-top"><span class="tag">{esc(offer['category'])}</span><span class="provider-mark">{esc(p['name'][:2].upper())}</span></div>
    <p class="eyebrow">{esc(p['name'])}</p><h3><a href="/deals/{esc(offer['id'])}/">{esc(offer['title'])}</a></h3>
    <p class="deal-value">{esc(value)}</p><p class="card-detail">{esc(offer.get('term_text') or 'Duration: see official terms')}</p>
    <dl><div><dt>After the offer</dt><dd>{esc(offer.get('renewal_text') or 'Not captured — check the source')}</dd></div>
    <div><dt>Checked</dt><dd>{esc(offer['checked_at'][:10])} UTC</dd></div></dl>
    <a class="card-link" href="/deals/{esc(offer['id'])}/">Read terms & evidence <span>→</span></a></article>'''

def build(base_url, local=False):
    u = urlsplit(base_url)
    if (u.scheme != 'https' and not (local and u.hostname in ('127.0.0.1','localhost'))) or not u.netloc or u.path not in ('','/'):
        raise ValueError('Set the actual HTTPS site origin; use --local only for localhost previews')
    base_url = base_url.rstrip('/')
    config, providers, dataset, money = load('config/site.json'), load('config/providers.json'), load('data/offers.json'), load('config/monetization.json')
    index = {p['id']: p for p in providers}; states = {s['id']: s for s in dataset['sources']}
    now = dt.datetime.now(dt.timezone.utc)
    active = [o for o in dataset['offers'] if fresh(o, now)]
    site = ROOT / 'site'; site.mkdir(exist_ok=True)
    # Only clear previously generated files inside this exact project's site directory.
    for child in site.iterdir():
        if child.is_dir(): shutil.rmtree(child)
        else: child.unlink()
    routes = []
    schema_history = load('data/history.json') if (ROOT/'data/history.json').exists() else []
    def write(path, title, description, body, noindex=False):
        for brand in ('hostinger', 'namecheap', 'godaddy'):
            if path == '/coupons/' + brand + '/':
                layer = dynamic_layer(brand, now)
                if layer:
                    if '<!-- dynamic-deals -->' in body:
                        body = body.replace('<!-- dynamic-deals -->', layer, 1)
                    else:
                        head_end = body.index('</h1>') + len('</h1>')
                        body = body[:head_end] + layer + body[head_end:]
        for provider in providers:
            if path == '/providers/'+provider['id']+'/' and provider.get('coupon_page'):
                body += '<section class="prose"><h2>Official coupon and promo evidence</h2><p><a href="'+provider['coupon_page']+'">'+esc(provider['coupon_title'])+'</a></p></section>'
        if path == '/':
            body += '<section class="prose"><h2>Official coupon and promo guides</h2>' + ''.join('<p><a href="'+p['coupon_page']+'">'+esc(p['coupon_title'])+'</a></p>' for p in providers if p.get('coupon_page')) + '</section>'
        page = template('base.html', title=esc(title), description=esc(description), body=body,
            coupon_nav=('<nav class="prose" aria-label="Coupon directory"><a href="/coupons/">Coupon and promo codes</a></nav>' if path in ('/coupons/hostinger/', '/coupons/godaddy/') else ''),
            jsonld=structured_data(path,body,base_url,config,providers,active,schema_history),
            canonical=esc(base_url + path), robots='noindex,follow' if noindex else 'index,follow',
            brand=esc(config['brand']), checked=esc(dataset['generated_at'][:10]))
        dest = site / path.lstrip('/') / 'index.html'; dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(page,encoding='utf-8'); routes.append(path)
    clouds = [o for o in active if o['category'] == 'Cloud & VPS']
    hosts = [o for o in active if o['category'] != 'Cloud & VPS']
    placements = []
    for sponsor in money.get('sponsors', []):
        if sponsor.get('approved') is True and sponsor.get('reviewed_at'):
            placements.append('<article class="notice"><p class="eyebrow">SPONSORED</p><h3>'+esc(sponsor['name'])+'</h3><p>'+esc(sponsor['description'])+'</p>'+outbound(sponsor['url'],'Visit sponsor',True)+'</article>')
    product = money.get('digital_product')
    if product and product.get('approved') is True and product.get('reviewed_at'):
        placements.append('<article class="notice"><p class="eyebrow">OUR DIGITAL PRODUCT</p><h3>'+esc(product['name'])+'</h3><p>'+esc(product['description'])+'</p>'+outbound(product['url'],'View product')+'</article>')
    write('/', 'HostingDealsGo — Hosting deals, with the receipts', config['description'], template('index.html',
        offer_count=len(active), provider_count=len(providers),
        cloud_cards=''.join(card(o,index,money) for o in clouds) or '<p>No freshly observed cloud offers. Check provider status below.</p>',
        hosting_cards=''.join(card(o,index,money) for o in hosts) or '<p>No freshly observed hosting offers.</p>',
        provider_rows=''.join(f'<a class="provider-row" href="/providers/{p["id"]}/"><strong>{esc(p["name"])}</strong><span>{esc(states.get(p["id"],{}).get("status","unknown").replace("_"," "))}</span><span>→</span></a>' for p in providers)) + ''.join(placements) + '<section class="prose"><h2>Renewal price evidence</h2><p><a href="/renewals/godaddy/">GoDaddy renewal coupons, prices and existing-customer discounts — official evidence</a></p><p><a href="/renewals/bluehost/">Bluehost renewal prices, coupons and automatic billing — official evidence</a></p></section>')
    write('/renewals/godaddy/', 'GoDaddy Renewal Coupon, Promo Codes and Domain Renewal Prices | HostingDealsGo',
        'Official US GoDaddy renewal prices, membership tiers, registration terms and three sourced customer reports.',
        (ROOT / 'content/godaddy-renewal.html').read_text(encoding='utf-8'))
    write('/renewals/bluehost/', 'Bluehost Renewal Prices, Coupons and Auto-Renewal Charges | HostingDealsGo',
        'Official Bluehost introductory versus renewal prices, billing descriptions and three unverified personal reports.',
        (ROOT / 'content/bluehost-renewal.html').read_text(encoding='utf-8'))
    write('/coupons/', 'Coupon and promo codes | HostingDealsGo',
        'Browse sourced coupon and promo code evidence by web hosting, cloud and VPS, or domain registrar.',
        (ROOT / 'content/coupons-index.html').read_text(encoding='utf-8'))
    for provider in providers:
        if provider.get('coupon_page'):
            write(provider['coupon_page'], provider['coupon_title']+' | HostingDealsGo',
                'Official codes, offer eligibility, renewal limits and refund evidence for '+provider['name']+'.',
                (ROOT / ('content/'+provider['id']+'-promo.html')).read_text(encoding='utf-8'))
    for p in providers:
        if p['id'] == 'godaddy':
            write('/providers/godaddy/', 'GoDaddy renewal prices and source status | HostingDealsGo',
                'Official renewal-price evidence and GoDaddy source status.',
                '<section class="page-head"><h1>GoDaddy domain renewal evidence</h1><p><a href="/renewals/godaddy/">Read the GoDaddy renewal coupon and price guide</a></p><p>The guide separates introductory prices, renewal tiers, paid membership and customer reports.</p></section>' +
                '<section class="prose"><h2>Source status</h2><p>The scheduled offer monitor last recorded an access problem; the guide uses a separate dated manual verification of public official pages.</p><p><a href="/sources/">View the scheduled source record</a> · <a href="/renewals/godaddy/#official-table">Official price and renewal-rule evidence</a></p></section>')
            continue
        if p['id'] == 'namecheap':
            write('/providers/namecheap/', 'Namecheap Domain Renewal Prices vs First-Year Registration | HostingDealsGo',
                'Verified Namecheap .com renewal pricing, first-year offers, ICANN fees and official source evidence.',
                (ROOT / 'content/namecheap-renewal.html').read_text(encoding='utf-8'))
            continue
        offers = [o for o in active if o['provider'] == p['id']]
        s = states.get(p['id'],{})
        links = ' '.join(outbound(url,'Official offer source') for url in p['offer_sources'])
        write('/providers/' + p['id'] + '/', p['name'] + ' offers & source status | HostingDealsGo',
            'Official offers and extraction status for ' + p['name'], template('provider.html',
            name=esc(p['name']), status=esc(s.get('status','unknown').replace('_',' ')),
            note=esc(p.get('note') or 'We publish only offers whose configured fields and restrictions remain readable in the official source.'),
            cards=''.join(card(o,index,money) for o in offers) or '<div class="notice">No fresh offer is published for this provider. This does not mean there are no offers; the source may block access, need JavaScript, redirect regions, or have changed.</div>',
            checked=esc(s.get('checked_at','Not checked')), js_mode=esc(s.get('js_mode','unknown').replace('_',' ')),
            source_links=links, sitemaps=''.join('<li>'+outbound(u,'Advertised sitemap')+'</li>' for u in s.get('sitemaps',[])),
            feeds=''.join('<li>'+outbound(u,'Advertised feed')+'</li>' for u in s.get('feeds',[])) or '<li>No feed discovered in the inspected home page.</li>') + ('<section class="prose"><h2>Renewal evidence</h2><p><a href="/renewals/bluehost/">Bluehost renewal price and auto-renewal guide</a></p></section>' if p['id']=='bluehost' else ''))
    for offer in dataset['offers']:
        live = fresh(offer, now)
        url, sponsored = target(offer, money)
        values = [('Displayed offer',offer.get('price_text') or offer.get('benefit_text') or offer.get('discount_text')),
            ('Discount',offer.get('discount_text')),('Commitment / duration',offer.get('term_text')),
            ('Renewal / after promotion',offer.get('renewal_text')),('Coupon code',offer.get('code')),
            ('Eligible plans',offer.get('eligibility_text')),
            ('Currency code',offer.get('currency')),('Starts',offer.get('valid_from')),('Ends',offer.get('valid_until'))]
        write('/deals/'+offer['id']+'/',offer['title']+' | HostingDealsGo',offer['title']+' — source, limitations and renewal context.',
            template('deal.html',title=esc(offer['title']), provider=esc(index[offer['provider']]['name']),
            provider_id=esc(offer['provider']), status='Observed on the official source' if live else 'Archived — no fresh verification',
            checked=esc(offer['checked_at']), fields=''.join(f'<div><dt>{esc(k)}</dt><dd>{esc(v) if v else "Not captured from the source"}</dd></div>' for k,v in values),
            evidence=esc(offer['evidence']), terms=''.join('<li>'+esc(t)+'</li>' for t in offer['terms_evidence']),
            source_link=outbound(offer['source_url'],'Read the official source'),
            offer_link=outbound(url,'Visit offer'+(' (affiliate link)' if sponsored else ''),sponsored),
            button_note='We may earn a commission through this link.' if sponsored else 'Direct official link. No affiliate tracking configured.'), noindex=not live)
    rows = ''.join(f'<tr><td><a href="/deals/{o["id"]}/">{esc(o["title"])}</a></td><td>{esc(o.get("price_text") or o.get("benefit_text") or o.get("discount_text"))}</td><td>{esc(o.get("term_text") or "Not captured")}</td><td>{esc(o.get("renewal_text") or "Check official terms")}</td><td>{esc(o.get("valid_until") or "Not stated / not captured")}</td><td>{esc(o["checked_at"][:10])}</td></tr>' for o in active)
    write('/compare/','Compare introductory offers & renewal context | HostingDealsGo','Compare displayed offers without treating different plans as equivalent.', template('compare.html',rows=rows))
    write('/methodology/','How we verify offers | HostingDealsGo','Our source, freshness and eligibility policy.', '''<section class="page-head"><p class="eyebrow">OUR STANDARD</p><h1>Evidence before a headline.</h1><p>Official sources, observable fields, explicit gaps.</p></section><div class="prose"><h2>What “observed” means</h2><p>A deterministic parser fetched the official page and matched the offer and its required restrictions. It does not mean a coupon passed checkout. We do not create accounts or test purchases.</p><h2>Region & currency</h2><p>This is an English-language site. The monitor requests en-US, rejects configured non-US redirects and retains price symbols exactly as displayed. A dollar symbol alone does not establish a currency code or eligibility in your country. Check the linked source and checkout.</p><h2>Dates & failure handling</h2><p>Checked dates are crawl times, not offer start dates. Missing start, expiry, currency or renewal fields remain unknown. Offers older than 48 hours, failed extractions and expired offers are excluded from the current list when the site is rebuilt. Archived pages retain their original verification date. If updates stop, refer to that date before relying on an offer.</p><h2>Sources & independence</h2><p>We use official public pages, honor robots rules, and do not bypass TLS checks, logins or anti-bot challenges. Unknown markup is suppressed. Sitemap discovery helps identify potential sources; it does not prove an offer.</p><h2>Pricing context</h2><p>Monthly introductory rates can require full-term prepayment. Taxes, extras, renewals and overages may be additional. Compare the total commitment, not just the monthly headline.</p><p><a href="/data/offers.json">Download the evidence dataset</a> · <a href="/sources/">Source health</a></p></div>''')
    statusrows=''.join(f'<tr><td><a href="/providers/{p["id"]}/">{esc(p["name"])}</a></td><td>{esc(states.get(p["id"],{}).get("status","unknown"))}</td><td>{esc(states.get(p["id"],{}).get("js_mode","unknown"))}</td><td>{esc(states.get(p["id"],{}).get("checked_at",""))}</td></tr>' for p in providers)
    write('/sources/','Official source health | HostingDealsGo','Status of each official source.', '<section class="page-head"><p class="eyebrow">OPEN RECORD</p><h1>Every source. Including the gaps.</h1><p>A failed fetch is not evidence that a provider has no deal.</p></section><div class="table-wrap"><table><thead><tr><th>Provider</th><th>Status</th><th>JavaScript needed?</th><th>Attempted UTC</th></tr></thead><tbody>'+statusrows+'</tbody></table></div>')
    affiliate_note = 'Approved affiliate links are configured.' if any(v.get('approved') for v in money['affiliate_links'].values()) else 'No affiliate tracking links are configured at launch; offer buttons point to official sources.'
    sponsor_note = 'Sponsored placements are active and labeled.' if any(s.get('approved') for s in money.get('sponsors',[])) else 'No paid placement is active.'
    write('/disclosure/','Disclosure & privacy | HostingDealsGo','Affiliate, sponsorship and privacy disclosure.', '<section class="page-head"><h1>Disclosure & privacy</h1></section><div class="prose"><p>'+affiliate_note+'</p><p>When affiliate links are enabled, they are identified near the button and marked sponsored. We may receive a commission if you buy through them. This does not change the source evidence or guarantee the lowest price.</p><p>Paid placements are labeled Sponsored and are separate from the offer list. '+sponsor_note+'</p><p>Privacy notice effective date: <time datetime="2026-10-16">2026-10-16</time>.</p><p>This site uses Google Analytics 4 (GA4) for traffic statistics. GA4 uses first-party cookies: <code>_ga</code> to distinguish users and <code>_ga_&lt;container-id&gt;</code> to persist session state. Browser settings or blocking tools may prevent these cookies from being set. <a href="https://support.google.com/analytics/answer/11397207?hl=en" rel="noopener noreferrer">Google Analytics cookie documentation</a>.</p><p>This site has no newsletter forms. The hosting provider may process network logs; merchant sites have their own policies.</p></div>')
    history = load('data/history.json') if (ROOT/'data/history.json').exists() else []
    changes = ''.join('<article class="notice"><p class="eyebrow">'+esc(h['observed_at'])+'</p><h3>'+esc(h['title'])+'</h3><p>'+('First observation; no earlier price claim.' if h['before'] is None else 'Changed fields: '+esc(', '.join(k for k,v in h['after'].items() if h['before'].get(k)!=v)))+'</p>'+outbound(h['source_url'],'Official evidence source')+'</article>' for h in reversed(history[-50:]))
    write('/changes/','Observed offer changes | HostingDealsGo','Changes detected in official source fields.', '<section class="page-head"><p class="eyebrow">OBSERVATION LOG</p><h1>What changed, and when.</h1><p>Detection dates are not provider announcement dates. Source removal can also mean a failed fetch or a changed layout.</p></section><div class="deal-grid">'+(changes or '<p>No previous comparable snapshots yet.</p>')+'</div><p><a href="/data/history.json">Download the change log →</a></p>')
    program_list=''.join('<li>'+outbound(p['affiliate_program_url'],p['name']+' official affiliate program')+'</li>' for p in providers if p.get('affiliate_program_url'))
    write('/about/','About HostingDealsGo | HostingDealsGo','An independent index of official hosting offers.', '<section class="page-head"><p class="eyebrow">HostingDealsGo</p><h1>Spend less time decoding the deal.</h1><p>We put the introductory offer, renewal context and source evidence in one place.</p></section><div class="prose"><p>Independent, newly launched, and focused on official hosting, cloud and VPS offers. We make no claims of operating history, special partnerships or checkout tests we have not performed.</p><h2>Official partner programs</h2><p>These links document public programs. A listing is not approval or an active partnership.</p><ul>'+program_list+'</ul></div>')
    shutil.copytree(ROOT / 'assets',site / 'assets')
    (site/'data').mkdir(); (site/'data/offers.json').write_text(json.dumps(dataset,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    dynamic_path = ROOT / 'data/dynamic-deals.json'
    if dynamic_path.exists(): shutil.copyfile(dynamic_path, site / 'data/dynamic-deals.json')
    (site/'data/health.json').write_text(json.dumps(load('data/health.json'),indent=2)+'\n',encoding='utf-8')
    (site/'data/history.json').write_text(json.dumps(history,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    export=io.StringIO(); writer=csv.writer(export); fields=['provider','title','price_text','discount_text','term_text','renewal_text','valid_until','checked_at','source_url']
    writer.writerow(fields)
    for o in active: writer.writerow([o.get(k) or '' for k in fields])
    (site/'data/offers.csv').write_text(export.getvalue(),encoding='utf-8')
    sitemap=ET.Element('urlset',xmlns='http://www.sitemaps.org/schemas/sitemap/0.9')
    for route in routes:
        if route.startswith('/deals/') and not any(route=='/deals/'+o['id']+'/' for o in active): continue
        item=ET.SubElement(sitemap,'url');ET.SubElement(item,'loc').text=base_url+route
        ET.SubElement(item,'lastmod').text=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    ET.ElementTree(sitemap).write(site/'sitemap.xml',encoding='utf-8',xml_declaration=True)
    (site/'robots.txt').write_text('User-agent: *\nAllow: /\nSitemap: '+base_url+'/sitemap.xml\n',encoding='utf-8')
    rss=ET.Element('rss',version='2.0'); channel=ET.SubElement(rss,'channel')
    for key,val in [('title','HostingDealsGo official offers'),('link',base_url),('description',config['description'])]: ET.SubElement(channel,key).text=val
    for o in active:
        item=ET.SubElement(channel,'item');url=base_url+'/deals/'+o['id']+'/'
        for key,val in [('title',o['title']),('link',url),('guid',url),('description',(o.get('price_text') or o.get('benefit_text') or o.get('discount_text') or '')+' — check official terms.')]: ET.SubElement(item,key).text=val
    ET.ElementTree(rss).write(site/'feed.xml',encoding='utf-8',xml_declaration=True)
    (site/'404.html').write_text(template('base.html',title='Page not found | HostingDealsGo',description='Page not found',body='<section class="page-head"><h1>That page has moved.</h1><p><a href="/">Browse current offers →</a></p></section>',canonical=esc(base_url+'/404.html'),robots='noindex,follow',brand='HostingDealsGo',checked=esc(dataset['generated_at'][:10])),encoding='utf-8')
    (site/'_headers').write_text('/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n  Content-Security-Policy: default-src \'self\'; style-src \'self\'; img-src \'self\' data: https://*.google-analytics.com https://*.googletagmanager.com; script-src \'self\' \'sha256-a2T61H+qMeCOZd11/F81mwLDJup/hSxLI08cqeVjyfk=\' https://www.googletagmanager.com; connect-src \'self\' https://*.google-analytics.com https://*.analytics.google.com https://*.googletagmanager.com; frame-ancestors \'none\'; base-uri \'self\'\n',encoding='utf-8')
    print(f'Built {len(routes)} pages, {len(active)} fresh observed offers at {base_url}')
    return site

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url');parser.add_argument('--local',action='store_true');args=parser.parse_args()
    origin=args.base_url or os.environ.get('SITE_URL') or load('config/site.json')['site_url'] or os.environ.get('CF_PAGES_URL')
    if not origin: parser.error('Set SITE_URL, CF_PAGES_URL, or --base-url to the actual site origin.')
    build(origin,args.local)
