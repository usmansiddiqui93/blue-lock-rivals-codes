# blue-lock-rivals-codes.com

Light-theme, fully automated Blue Lock: Rivals codes site. Static HTML, hosted free on GitHub Pages, updated by GitHub Actions every 30 minutes. No server, no database, no dependencies beyond Python's standard library.

## How the automation works

Every 30 minutes `.github/workflows/update-and-deploy.yml`:

1. Runs the parser tests (a broken parser never publishes).
2. Runs `scripts/update_codes.py`, which reads every page in `data/sources.json` (respecting robots.txt) and extracts **only** code strings and reward counts.
3. **Publishes a new code only when ≥ 2 sources list it as active and none list it as expired.** One stale or wrong tracker can't add a code on its own.
4. **Expires a code** when ≥ 2 sources list it as expired, or when every source stops listing it for 12 runs (6 hours).
5. Reads the game's Roblox title (e.g. `[Don Lorenzo] Blue Lock: Rivals`) and logs new updates to the Update Log automatically.
6. Commits any data change, rebuilds the site and deploys it.

**Safety rail:** if one run tries to add more than 6 or expire more than 8 codes (usually a source changed its layout), nothing is written and the Action goes red. Check the log; if the change is real, run the workflow manually with **force** ticked.

## One-time setup (≈10 minutes)

1. Create a new GitHub repo (public is free for Pages) and push this folder to `main`.
2. Repo **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. Repo **Settings → Actions → General → Workflow permissions → Read and write**.
4. **Custom domain:** Settings → Pages → Custom domain → `blue-lock-rivals-codes.com`, then at your DNS provider:
   - `A` records for `@` → `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
   - `CNAME` for `www` → `<your-github-username>.github.io`
   - Tick **Enforce HTTPS** once the certificate is issued.
5. Actions tab → **Update codes & deploy → Run workflow** to do the first deploy.
6. Submit `https://blue-lock-rivals-codes.com/sitemap.xml` in Google Search Console.

### Optional
- **Discord alerts:** add a repo secret `DISCORD_WEBHOOK_URL` — new codes get posted to your server automatically.
- **AdSense:** set `"ads_enabled": true` in `data/site.json` once approved. `ads.txt` is generated for you.
- **Author photo:** drop `author.png` into `assets/`.
- **Social preview image:** drop a 1200×630 `og.png` into `assets/`.

## Editing content

| What | File |
|---|---|
| Codes (manual add/fix) | `data/codes.json` |
| Sources watched | `data/sources.json` |
| Styles & rarities | `data/styles.json` |
| Flows & effects | `data/flows.json` |
| Tier list | `data/tierlist.json` |
| Update log | `data/updates.json` |
| Site name, links, nav, AdSense | `data/site.json` |
| Page text & layout | `scripts/build.py` |
| Design | `assets/style.css` |

Edit on github.com and commit — the site rebuilds automatically on every push.

## Pages

`/` codes · `/expired-codes/` · `/how-to-redeem/` · `/free-spins/` · `/styles/` · `/flows/` · `/tier-list/` · `/controls/` · `/beginners-guide/` · `/trello-discord/` · `/updates/` · `/guides/` · `/about/` · `/privacy-policy.html` · `404` — plus `sitemap.xml`, `feed.xml` (RSS), `robots.txt`, `ads.txt` and a public `api/codes.json`.

## Local commands

```bash
python scripts/build.py                                   # build into dist/
python -m http.server -d dist 8000                        # preview at localhost:8000
python tests/test_updater.py                              # parser + logic tests
python scripts/update_codes.py --dry-run                  # see what a live run would change
python scripts/update_codes.py --fixtures tests/fixtures  # offline run
```
