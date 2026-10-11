"""Evidence-limited Schema.org graphs; no inference about currency or stock."""
from html.parser import HTMLParser
import datetime as dt
import json
import re

class Heading(HTMLParser):
    def __init__(self):
        super().__init__(); self.inside=False; self.parts=[]
    def handle_starttag(self, tag, attrs):
        if tag=='h1': self.inside=True
    def handle_endtag(self, tag):
        if tag=='h1': self.inside=False
    def handle_data(self, text):
        if self.inside: self.parts.append(text)

def offer_node(offer, origin, provider):
    url=origin+'/deals/'+offer['id']+'/'
    node={'@type':'Offer','@id':url+'#offer','name':offer['title'],'url':offer['offer_url'],
          'itemOffered':{'@type':'Service','@id':url+'#service','name':offer['title'],
                         'provider':{'@type':'Organization','name':provider['name']}}}
    # Only explicit displayed monetary prices; percentage, credit and free claims are not prices.
    text=offer.get('price_text') or ''
    m=re.fullmatch(r'\s*\$\s*(\d+(?:\.\d+)?)\s*/mo\s*',text)
    if m and m.group(1) in offer.get('evidence',''):
        node['price']=m.group(1)
    if offer.get('currency') and re.fullmatch(r'[A-Z]{3}',offer['currency']):
        node['priceCurrency']=offer['currency']
    if offer.get('valid_until'):
        try:
            dt.date.fromisoformat(offer['valid_until'])
            node['priceValidUntil']=offer['valid_until']
        except ValueError: pass
    # Observed or checkout-untested does not establish InStock or another availability state.
    return node

def item_list(entries, identity):
    return {'@type':'ItemList','@id':identity,'itemListElement':[
        {'@type':'ListItem','position':i,'name':name,'url':url}
        for i,(name,url) in enumerate(entries,1)]}

def render(path, body, origin, config, providers, active, history):
    if path=='/404.html': return ''
    heading=Heading();heading.feed(body);name=''.join(heading.parts).strip()
    url=origin+path; organization=origin+'/#organization'; website=origin+'/#website'
    graph=[{'@type':'Organization','@id':organization,'name':config['brand'],'url':origin+'/',
            'publishingPrinciples':origin+'/methodology/'},
           {'@type':'WebSite','@id':website,'name':config['brand'],'url':origin+'/',
            'publisher':{'@id':organization}},
           {'@type':'WebPage','@id':url+'#webpage','name':name,'url':url,
            'isPartOf':{'@id':website},'publisher':{'@id':organization}}]
    page=graph[2]; index={p['id']:p for p in providers}
    crumbs=[(config['brand'],origin+'/')]
    if path.startswith('/deals/'):
        found=next((o for o in active if path=='/deals/'+o['id']+'/'),None)
        if found:
            p=index[found['provider']]
            crumbs.append((p['name'],origin+'/providers/'+p['id']+'/'))
            node=offer_node(found,origin,p);graph.append(node);page['mainEntity']={'@id':node['@id']}
    elif path.startswith('/providers/'):
        p=next(p for p in providers if path=='/providers/'+p['id']+'/')
        node={'@type':'Service','@id':url+'#service','name':p['name'],'url':url,
              'provider':{'@type':'Organization','name':p['name']}}
        offers=[offer_node(o,origin,p) for o in active if o['provider']==p['id']]
        if offers: node['offers']=offers
        graph.append(node);page['mainEntity']={'@id':node['@id']}
    entries=None
    if path=='/':entries=[(p['name'],origin+'/providers/'+p['id']+'/') for p in providers]
    elif path=='/compare/':entries=[(o['title'],origin+'/deals/'+o['id']+'/') for o in active]
    elif path=='/sources/':entries=[(p['name'],origin+'/providers/'+p['id']+'/') for p in providers]
    elif path=='/changes/':entries=[(h['title'],h['source_url']) for h in reversed(history[-50:])]
    if entries is not None:
        node=item_list(entries,url+'#list');graph.append(node);page['mainEntity']={'@id':node['@id']}
    if path!='/':
        crumbs.append((name,url))
        node={'@type':'BreadcrumbList','@id':url+'#breadcrumb','itemListElement':[
            {'@type':'ListItem','position':i,'name':n,'item':u} for i,(n,u) in enumerate(crumbs,1)]}
        graph.append(node);page['breadcrumb']={'@id':node['@id']}
    data=json.dumps({'@context':'https://schema.org','@graph':graph},ensure_ascii=False,separators=(',',':'))
    # JSON is a data block; escape HTML delimiters to prevent a source string terminating the tag.
    data=data.replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    return '<script type="application/ld+json">'+data+'</script>'
