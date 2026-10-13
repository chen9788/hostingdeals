"""Check every sitemap route is reachable via actual generated HTML links."""
from pathlib import Path
from html.parser import HTMLParser
from collections import deque
from urllib.parse import urljoin, urlsplit
import json
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent
class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.hrefs=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':
            self.hrefs.extend(v for k,v in attrs if k=='href' and v)

def inspect():
    site=ROOT/'site'
    urls=[x.text for x in ET.parse(site/'sitemap.xml').findall('.//{*}loc')]
    origin=urlsplit(urls[0]); targets={urlsplit(u).path for u in urls}
    paths={'/':[]}; queue=deque(['/'])
    while queue:
        route=queue.popleft(); f=site/route.lstrip('/')/'index.html'
        if not f.exists(): continue
        parser=Links(); parser.feed(f.read_text(encoding='utf-8'))
        for href in parser.hrefs:
            u=urlsplit(urljoin(urls[0].rstrip('/')+route,href))
            if (u.scheme,u.netloc)!=(origin.scheme,origin.netloc): continue
            if u.path in targets and u.path not in paths:
                paths[u.path]=paths[route]+[u.path]; queue.append(u.path)
    missing=sorted(targets-paths.keys())
    rules=json.loads((ROOT/'config/inspection.json').read_text(encoding='utf-8'))
    too_deep=[u for u in rules['critical_routes'] if u not in paths or len(paths[u])>rules['max_clicks']]
    if missing or too_deep:
        raise SystemExit('Orphans: '+repr(missing)+'; critical routes beyond click limit: '+repr(too_deep))
    print(f'PASS: {len(targets)} sitemap routes reachable; {len(rules["critical_routes"])} coupon routes within {rules["max_clicks"]} clicks')
    return paths

if __name__=='__main__': inspect()
