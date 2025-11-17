# MakeItEASY

Find the best prices for makeup products in Lebanon (and beyond) without
scraping social media platforms.

This repository now ships a small Python helper that talks to the free
[Makeup API](http://makeup-api.herokuapp.com/api/v1/products.json) along with a
Google Custom Search instance that uses the search engine id
`151662c5c18ba4c4c`.

## Requirements

* Python 3.9+
* `requests` (install via `pip install -r requirements.txt`)

## Usage

Run the CLI by passing the product query. Optional arguments let you narrow the
results by brand, product type, tags, and price. You can also append
`--include-google` to surface relevant shopping links through the provided
Google Custom Search engine.

```bash
python makeiteasy.py "maybelline lipstick" \
  --brand maybelline \
  --product-type lipstick \
  --price-max 15 \
  --product-tags vegan cruelty-free \
  --include-google
```

Environment variables `GOOGLE_API_KEY` and `GOOGLE_CSE_ID` override the defaults
if you need to supply your own credentials.
