"""Check static routes, UTF-8, sitemap origins and published dataset integrity."""
import argparse,json,os
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit,unquote
import xml.etree.ElementTree as ET
from scraper import official
ROOT=Path(__file__).resolve().parent
class Links(HTMLParser):
    def __init__(self):super().__init__();self.urls=[]
    def handle_starttag(self,t,a):
        d=dict(a)
        for k in ('href','src'):
            if k in d:self.urls.append(d[k])
def check(base_url):
    site=ROOT/'site'; origin=urlsplit(base_url);errors=[]
    pages=list(site.rglob('*.html'))
    for path in pages:
        text=path.read_text(encoding='utf-8')
        if '\ufffd' in text:errors.append(f'Invalid replacement character: {path}')
        if 'charset="utf-8"' not in text:errors.append(f'Missing charset: {path}')
        links=Links();links.feed(text)
        for url in links.urls:
            u=urlsplit(url)
            if u.scheme in ('https','http'):
                if u.netloc != origin.netloc:continue
                url=u.path
            elif u.scheme:errors.append('Unexpected URL scheme: '+url);continue
            if url.startswith('#'):continue
            local=site/unquote(url.lstrip('/')).split('#')[0]
            if local.is_dir():local=local/'index.html'
            if not local.exists():errors.append(f'Broken local link: {path.name}: {url}')
    xml=ET.parse(site/'sitemap.xml')
    for n in xml.getroot():
        loc=n.find('{*}loc').text;u=urlsplit(loc)
        if (u.scheme,u.netloc)!=(origin.scheme,origin.netloc):errors.append('Foreign sitemap URL: '+loc)
        if not (site/u.path.lstrip('/')/'index.html').exists():errors.append('Missing sitemap route: '+loc)
    if 'Sitemap: '+base_url.rstrip('/')+'/sitemap.xml' not in (site/'robots.txt').read_text():errors.append('Wrong robots sitemap origin')
    data=json.loads((site/'data/offers.json').read_text(encoding='utf-8'))
    providers={p['id']:p for p in json.loads((ROOT/'config/providers.json').read_text())}
    ids=set()
    for o in data['offers']:
        if o['id'] in ids:errors.append('Duplicate offer ID')
        ids.add(o['id']);p=providers[o['provider']]
        if not official(o['source_url'],p['domains']):errors.append('Nonofficial evidence URL')
        if not o['evidence'] or not o['checked_at'] or not o['source_sha256']:errors.append('Incomplete evidence')
        if o['checkout_tested'] is not False:errors.append('Unsubstantiated checkout verification')
    if errors:raise SystemExit('\n'.join(errors))
    print(f'PASS: {len(pages)} HTML pages, internal links, UTF-8, sitemap origin, robots and offer provenance')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base-url');a=p.parse_args()
    origin=a.base_url or os.environ.get('SITE_URL') or json.loads((ROOT/'config/site.json').read_text())['site_url']
    if not origin:p.error('Set the actual site origin with --base-url, SITE_URL or config/site.json')
    check(origin)
