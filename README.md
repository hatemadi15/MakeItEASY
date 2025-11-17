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

Run the CLI by passing the product query. Optional arguments let you narrow the
results by brand, product type, tags, price, and rating. Add
`--include-google --google-results 3` to surface relevant shopping links
through the provided Google Custom Search engine.

```bash
python makeiteasy.py "maybelline lipstick" \
  --brand maybelline \
  --product-type lipstick \
  --price-max 15 \
  --product-tags vegan cruelty-free \
  --max-results 10 \
  --sort-by rating --descending \
  --include-google --google-results 3
```

When results are found, the CLI prints a quick summary (count, price range,
average rating), a compact table, and then a detailed per-product view with
links and descriptions.

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
