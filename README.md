# MakeItEASY

Find the best prices for makeup products in Lebanon (and beyond) without
scraping social media platforms.

This repository now ships a small Python helper that talks to the free
[Makeup API](http://makeup-api.herokuapp.com/api/v1/products.json) along with a
Google Custom Search instance that uses the search engine id
`151662c5c18ba4c4c`.

## Requirements

* Python 3.9+
* (Optional) `requests` — install via `pip install -r requirements.txt` for faster HTTP calls.

## Usage

### Web UI (MVP)

If you prefer a point-and-click experience, run the built-in mini web server:

```bash
python app.py
```

Then open http://localhost:8000 to access a responsive dashboard that splits the
experience into two cards:

1. **EasyDirectory** — accepts the same filters as the CLI (query, brand, type,
   category, tags, price, and rating ranges) and returns matching products
   directly from the free Makeup API.
2. **EasySearch** — runs the provided query through the Google Custom Search
   Engine, limits the matches to a recent timeframe (past week/month/quarter),
   and extracts structured pricing data so you can quickly spot the cheapest
   merchants for that query. Results that don't advertise a price are collapsed
   behind a disclosure widget so they never clutter the main ranking.

Errors from blocked proxies or invalid input are surfaced inline so you always
know why a search failed. No additional dependencies are required beyond the
standard library.

### CLI Helper

Run the CLI by passing the product query. Optional arguments let you narrow the
results by brand, product type, tags, price, and rating. Add
`--include-google --google-results 3` to surface relevant shopping links through
EasySearch (the provided Google Custom Search engine), or use
`--google-cheapest` to rank those links by the lowest extracted price. The
Google helpers now limit results to the most recent month by default; adjust the
window with `--google-date-restrict d7|m1|m3|y1|none`.

```bash
python makeiteasy.py "maybelline lipstick" \
  --brand maybelline \
  --product-type lipstick \
  --price-max 15 \
  --product-tags vegan cruelty-free \
  --max-results 10 \
  --sort-by rating --descending \
  --include-google --google-results 3 --google-cheapest
```

When results are found, the CLI prints a quick summary (count, price range,
average rating), a compact table, and then a detailed per-product view with
links and descriptions. When `--google-cheapest` is enabled the CLI will reuse
the Google Custom Search response to pull out structured price metadata so you
can immediately see which merchant is the most affordable for the same query.

### Guided interactive mode

If you prefer prompts, skip the query and use `--interactive` to be guided
through each filter step:

```bash
python makeiteasy.py --interactive
```

You'll be asked for the search phrase, brand, price range, ratings, and tags.
Press Enter at any prompt to skip that filter.

Environment variables `GOOGLE_API_KEY` and `GOOGLE_CSE_ID` override the defaults
if you need to supply your own credentials.

### Troubleshooting

If searches immediately fail with a message such as
`HTTP 403 Forbidden — the network proxy http://proxy:8080 blocked outbound access to http://makeup-api.herokuapp.com/api/v1/products.json.`,
you are running inside a network that disallows outbound calls to Heroku (this
sandbox uses a restrictive proxy). Re-run the CLI from a machine with
unrestricted HTTP/S egress or configure your proxy to allow connections to the
Makeup API host.
