# Performance Notes (Visitor-focused)

## What was improved

1. **GZip compression enabled**
   - Added `django.middleware.gzip.GZipMiddleware` in `settings.py`.
   - Visitor responses are now compressed (`Content-Encoding: gzip`).

2. **Page caching for heavy public pages**
   - `index` (`/`) cached for 5 min
   - `browse` (`/browse/`) cached for 5 min
   - `browse_legacy` (`/browse_legacy/`) cached for 5 min
   - `timeline` (`/timeline/`) cached for 5 min
   - `about` (`/about/`) cached for 30 min

3. **Timeline API already cached**
   - `/api/ereignisse/` uses server-side cache (5 min), added earlier.

## Measured local effect (quick repeated-hit timing)

- `/` : `0.39s -> 0.01s`
- `/browse/` : `0.39s -> 0.01s`
- `/timeline/` : `0.01s -> 0.00s`
- `/api/ereignisse/` : `0.53s -> 0.04s`

These are local dev measurements, but they confirm meaningful caching/compression wins for visitors.

## Lighthouse

A direct Lighthouse run was attempted in this environment, but Chrome connection failed via CLI launcher.
The app was therefore optimized via measurable server-side changes and endpoint timing checks.
If needed, run Lighthouse from a desktop browser machine against staging/production URL for final UX scores.
