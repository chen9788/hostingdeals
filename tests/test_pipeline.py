import datetime as dt,json,unittest
from pathlib import Path
import scraper,build
PROVIDERS=json.loads((Path(__file__).parents[1]/'config/providers.json').read_text())
class PipelineTests(unittest.TestCase):
    def test_markup_and_terms_must_match_together(self):
        p=next(p for p in PROVIDERS if p['id']=='cloudways')
        text='You will get 40% off for 4 months on all plans. This offer is for new users who sign up. Once the promotional period ends, standard pricing applies. No. This offer is not available to existing Cloudways customers.'
        found,status=scraper.extract(p,'<p>'+text+'</p>',p['offer_sources'][0],'2026-10-11T00:00:00+00:00')
        self.assertEqual(status,'ok');self.assertEqual(found[0]['discount_text'],'40% off')
        self.assertIsNone(found[0]['price_text']);self.assertFalse(found[0]['checkout_tested'])
        self.assertEqual(scraper.extract(p,text.replace('This offer is for new users','A vague claim'),p['offer_sources'][0],'now')[0],[])
    def test_script_text_is_not_visible_offer_evidence(self):
        p=next(p for p in PROVIDERS if p['id']=='cloudways')
        self.assertEqual(scraper.extract(p,'<script>You will get 99% off for 4 months on all plans</script>',p['offer_sources'][0],'now')[0],[])
    def test_regional_redirect_is_suppressed(self):
        p=next(p for p in PROVIDERS if p['id']=='cloudways')
        self.assertEqual(scraper.extract(p,'text','https://eu.cloudways.com/','now')[1],'region_mismatch')
    def test_official_domain_boundary(self):
        self.assertFalse(scraper.official('https://cloudways.com.evil.example/', ['cloudways.com']))
        self.assertFalse(scraper.official('http://cloudways.com/', ['cloudways.com']))
        self.assertTrue(scraper.official('https://support.cloudways.com/', ['cloudways.com']))
    def test_stale_and_failed_offers_are_not_current(self):
        now=dt.datetime(2026,10,11,tzinfo=dt.timezone.utc)
        o={'status':'observed','checked_at':'2026-10-10T00:00:00+00:00','valid_until':None}
        self.assertTrue(build.fresh(o,now))
        self.assertFalse(build.fresh({**o,'status':'unavailable'},now))
        self.assertFalse(build.fresh({**o,'checked_at':'2026-10-07T00:00:00+00:00'},now))
        self.assertFalse(build.fresh({**o,'valid_until':'2026-10-09'},now))
        self.assertFalse(build.fresh({**o,'valid_until':'October someday'},now))
        self.assertFalse(build.fresh({**o,'valid_from':'2026-10-13'},now))
    def test_html_is_escaped(self):
        self.assertEqual(build.esc('<script>'), '&lt;script&gt;')
        with self.assertRaises(ValueError):build.outbound('javascript:alert(1)','Buy')
if __name__=='__main__':unittest.main()
