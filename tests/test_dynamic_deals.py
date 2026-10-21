import datetime as dt
import unittest
from dynamic_deals import current, official, parse

NOW = dt.datetime(2026, 10, 21, tzinfo=dt.timezone.utc)

class DynamicRules(unittest.TestCase):
    def item(self, **changes):
        item = dict(brand='hostinger', code='COUPONSPAGE', checked_at=NOW.isoformat(),
                    source_url='https://www.hostinger.com/coupons', status='officially_observed')
        item.update(changes)
        return item

    def test_unknown_expiry_not_assumed_expired(self):
        self.assertTrue(current(self.item(), NOW))

    def test_expiry_boundary_and_stale_failure(self):
        self.assertFalse(current(self.item(valid_until=NOW.isoformat()), NOW))
        self.assertFalse(current(self.item(), NOW + dt.timedelta(hours=49)))
        self.assertFalse(current(self.item(), NOW - dt.timedelta(seconds=1)))
        self.assertFalse(current(self.item(checked_at='broken'), NOW))
        self.assertFalse(current(self.item(checked_at='2026-10-21'), NOW))

    def test_source_and_html_injection(self):
        for url in ['https://hostinger.com.evil.test/', 'https://hostinger.com@evil.test',
                    'http://hostinger.com/coupons', 'https://user:password@hostinger.com/']:
            self.assertFalse(official('hostinger', url))
        self.assertFalse(current(self.item(code='<script>'), NOW))

    def test_strict_association_and_challenge(self):
        url = 'https://www.hostinger.com/coupons'
        good = parse('hostinger', 'Use coupon code COUPONSPAGE for 10% off', url, NOW.isoformat())
        self.assertEqual(good[0]['code'], 'COUPONSPAGE')
        self.assertIsNone(good[0]['valid_until'])
        self.assertEqual(good[0]['checkout_status'], 'not verified')
        self.assertFalse(parse('hostinger', 'COUPONSPAGE 90% off', url, NOW.isoformat()))
        self.assertFalse(parse('hostinger', 'Access denied Use code COUPONSPAGE for 10% off', url, NOW.isoformat()))

    def test_plan_discount_stays_with_its_product(self):
        text = "81% off\nPremium\nDescription\n'COUPONSPAGE' coupon applied\nUse coupon\nGet 48 months for $113.76.\n83% off\nUnlimited\nDescription\n'COUPONSPAGE' coupon applied\nUse coupon\nGet 48 months for $159.36."
        offers = parse('hostinger', text, 'https://www.hostinger.com/coupons', NOW.isoformat())
        self.assertEqual([(o['product'], o['discount'].split(' ')[0]) for o in offers], [('Premium', '81%'), ('Unlimited', '83%')])
        self.assertTrue(all('not incremental' in o['discount'] for o in offers))

    def test_namecheap_calendar_deadline_and_scope(self):
        text = ('Valid October 1 - October 31, 2026\n'
                'Discounted registration and transfer\nSee details below\nGHOSTDOT\nRegister domain →\n'
                'Promotional price applies to first-year registrations and transfers only and is not applicable for premium or aftermarket domains.')
        offers = parse('namecheap', text, 'https://www.namecheap.com/promos/coupons/', NOW.isoformat())
        self.assertEqual(len(offers), 1)
        item = offers[0]
        self.assertEqual(item['source_end_date'], '2026-10-31')
        self.assertIn('timezone not verified', item['expiry_note'])
        # Freshly fetched but past the conservative, separately labeled withdrawal cutoff.
        end = dt.datetime(2026, 10, 31, tzinfo=dt.timezone.utc)
        self.assertFalse(current({**item, 'checked_at': end.isoformat()}, end))
        self.assertTrue(current(item, NOW))
        self.assertFalse(parse('namecheap', text.replace('first-year', 'all-year'), item['source_url'], NOW.isoformat()))

if __name__ == '__main__': unittest.main()
