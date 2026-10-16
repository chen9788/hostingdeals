# hostingdeals

An English-language official-source index for hosting, cloud and VPS offers. Every published offer has source evidence and an observation date. Introductory terms and renewal fields stay separate. This is a new project; no fabricated operating history, traffic, backlinks, commissions or checkout tests.

**Production site:** https://hostingdealsgo.com

## Runtime

- Python 3.12 standard library only; no pip install, JavaScript execution, inference calls or paid APIs.
- Daily GitHub Actions fetch → deterministic parsing → JSON → static HTML → validation → commit.
- Cloudflare Pages Git integration builds and deploys when the repository changes.
- No user-managed API key. GitHub supplies its short-lived `GITHUB_TOKEN` for commits; Pages requires a one-time GitHub app authorization. Those are account authorizations, not inference keys.
- No Functions, Worker runtime, database or server. This site uses Google Analytics 4 (GA4) for traffic statistics. GA4 uses first-party cookies: `_ga` to distinguish users and `_ga_<container-id>` to persist session state. Browser settings or blocking tools may prevent these cookies from being set.

## Files

`scraper.py` monitors official allowlisted pages and advertised robots/sitemaps/feeds. `config/providers.json` contains reviewed source URLs and extraction rules. `data/offers.json` is replaced atomically at each update; `data/history.json` records substantive changes. `build.py` renders `templates/` to `site/`. `validate.py` checks routes, UTF-8, sitemap origins and evidence. `.github/workflows/update.yml` commits data and output daily at 06:23 UTC.

## Run locally

```sh
python -m unittest discover -s tests -v
python scraper.py
python build.py --base-url http://127.0.0.1:8765 --local
python validate.py --base-url http://127.0.0.1:8765
python -m http.server 8765 --directory site --bind 127.0.0.1
```

Never publish the localhost preview output. Rebuild with the actual production origin first.

## Publish to Cloudflare Pages

1. Create a public GitHub repository named `hostingdeals` and push these files on `main`. Public standard GitHub-hosted runners are the intended free path; check the current account/plan terms.
2. In Cloudflare, create a **Pages** project using Git integration, authorize access only to this repository, and select `main`.
3. Build command: `python build.py`; output directory: `site`; root directory: repository root. Set `PYTHON_VERSION=3.12`. No framework preset is needed.
4. For the first deployment, `CF_PAGES_URL` supplies the real Pages origin. After it succeeds, set `config/site.json.site_url` to the production `https://hostingdealsgo.com` origin. An optional GitHub repository Actions variable `SITE_URL` overrides it. The explicit value ensures production canonicals also stay correct on preview builds.
5. Allow Actions read/write repository contents if account policy currently prevents it. Run **Refresh official offers** manually and inspect the commit, source health, and Pages deployment.
6. Confirm external HTTP 200 at `/`, `/robots.txt`, `/sitemap.xml`, `/data/health.json` and a deal page. All sitemap URLs must use the actual production origin.

Official platform references: [Pages Git integration](https://developers.cloudflare.com/pages/configuration/git-integration/), [Pages build configuration](https://developers.cloudflare.com/pages/configuration/build-configuration/), [GitHub scheduled workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## What the monitor does and does not prove

The first direct crawl observed ten offers across six providers. Other providers remain listed with honest failure status. A2's site redirects to hosting.com; readable hosting plan prices were not found in the monitored response. SiteGround returned an EU page and was suppressed. Several official pages returned 403 or certificate failures. No security or anti-bot bypass is implemented.

The DigitalOcean trial is specifically **Agent Droplets (AI product)**, not a general VPS credit. Its benefit is not extrapolated to regular Droplets. Vultr's monitored documentation describes credits but does not state a credit amount; that field remains empty.

“Observed” means the official page still contains the configured offer and required restrictions, not that a coupon worked in checkout. A crawl date is not a promotion start date. Unknown price, currency, start/end date and renewal fields remain null. A dollar symbol alone is not proof of USD or US customer eligibility. Source text is quoted briefly with a digest and a source URL.

Robots restrictions are respected. An unreadable robots file suppresses that origin. Only transient network/server errors are retried. Changed markup is suppressed; discovery candidates do not automatically become deals. Prior failed offers remain archived with their original checked date and are excluded from the fresh list. Explicit expiry is respected; offers older than 48 hours are not current on rebuild. If automation stops entirely, the static page cannot detect that without a new build: always inspect the date.

GitHub can delay schedules or disable inactive schedules, and free-platform terms can change. No design can guarantee that an unattended site operates forever. Inspect workflow failure notifications, source health and Pages status. Update an extraction rule when a provider changes its layout; do not replace unknown fields with guesses.

## Stackable monetization, without invented partnerships

### Approved affiliate links

Official program entry pages discovered during the audit are recorded per provider in `config/providers.json`. Apply to relevant programs and review their current coupon-site, promotional, brand-bidding, email and disclosure rules. Approval, eligible products and commissions must come from the actual agreement; no commission number is hardcoded.

After approval, add the owner's issued link to `config/monetization.json`:

```json
{
  "affiliate_links": {
    "cloudways": {
      "url": "YOUR_ACTUAL_HTTPS_TRACKING_URL",
      "program_url": "https://www.cloudways.com/en/web-hosting-affiliate-program.php",
      "approved": true,
      "reviewed_at": "YOUR_ACTUAL_REVIEW_DATE"
    }
  },
  "sponsors": [],
  "digital_product": null
}
```

These illustrative placeholders are not deployable tracking links. The builder uses direct official links unless approval metadata is present. Affiliate buttons carry a disclosure and `rel=sponsored`. Keep source evidence linked directly to the official page.

### Clearly labeled sponsorships

After an actual agreement, add a sponsor object with `name`, `description`, `url`, `approved: true`, and a real `reviewed_at` date. Its card is labeled Sponsored and does not change the comparison data. No sponsorship is active initially.

### An actual digital product

The free evidence CSV and change log are useful outputs, not fake lead magnets. A future paid migration/renewal planning pack can be listed using a `digital_product` object with the same reviewed fields, once that product and checkout actually exist. There is no fabricated product or payment link at launch.

### Eventual asset sale

GA4 is enabled for traffic statistics, as described in the site's Disclosure & privacy notice. Record only verified analytics and revenue. Preserve repository history, source provenance, approved program agreements and reproducible builds for buyer due diligence. Platform accounts and affiliate approvals may require reapplication or provider consent on transfer. No sale valuation or income is promised.

## Useful content and links

The renewal-context comparison, source status, structured downloads and observation log are citable outputs. Make them accurate and useful; seek editorial links through actual usefulness. Do not automate spam outreach or invent backlinks. Domain age alone is not a ranking guarantee.

## Initial source audit

`data/seed-source-audit.json` records direct home/robots/offer checks, discovered official navigation links, redirects, and errors. The current public `/sources/` page reports the latest run. A failed fetch is not proof of no discount and cannot establish whether JavaScript is required.
