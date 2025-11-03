const API_BASE = `${window.location.origin.replace(/:\d+$/, ':8000')}`;

const searchButton = document.getElementById('search-button');
const queryInput = document.getElementById('query-input');
const countrySelect = document.getElementById('country-select');
const conditionSelect = document.getElementById('condition-select');
const resultsContainer = document.getElementById('results');
const statusLine = document.getElementById('status');
const template = document.getElementById('offer-template');
const detailsLayer = document.getElementById('details-layer');
const detailsClose = document.getElementById('details-close');
const detailsTitle = document.getElementById('details-title');
const detailsSummary = document.getElementById('details-summary');
const detailsBreakdown = document.getElementById('details-breakdown');
const detailsAssumptionsSection = document.getElementById('details-assumptions-section');
const detailsAssumptions = document.getElementById('details-assumptions');
const detailsConfidence = document.getElementById('details-confidence');
const detailsEvidence = document.getElementById('details-evidence');
const detailsScreenshot = document.getElementById('details-screenshot');

async function fetchOffers() {
  const query = queryInput.value.trim();
  if (!query) {
    statusLine.textContent = 'Enter a product to search for current prices.';
    return;
  }

  closeDetails();
  statusLine.textContent = 'Searching for live offers…';
  resultsContainer.classList.remove('empty');
  resultsContainer.innerHTML = '';

  const params = new URLSearchParams({ q: query });
  if (countrySelect.value) {
    params.append('country', countrySelect.value);
  }
  if (conditionSelect.value) {
    params.append('condition', conditionSelect.value);
  }

  try {
    const response = await fetch(`${API_BASE}/search?${params.toString()}`);
    if (response.status === 429) {
      const errorPayload = await response.json().catch(() => ({}));
      const retryAfter = errorPayload?.detail?.retry_after ?? 60;
      statusLine.textContent = `Too many requests. Please try again in ${retryAfter} seconds.`;
      resultsContainer.innerHTML = '';
      resultsContainer.classList.add('empty');
      return;
    }
    if (!response.ok) {
      throw new Error(`Search failed (${response.status})`);
    }
    const payload = await response.json();
    renderOffers(payload);
  } catch (error) {
    console.error(error);
    statusLine.textContent = "We couldn't fetch new prices right now. Showing cached results if available.";
    resultsContainer.innerHTML = '';
    resultsContainer.classList.add('empty');
  }
}

function renderOffers(payload) {
  const offers = payload.offers ?? [];
  if (!offers.length) {
    resultsContainer.classList.add('empty');
    resultsContainer.innerHTML = '<div class="empty-state">No offers found. Try another search.</div>';
    statusLine.textContent = '';
    return;
  }

  const conditionLabel = conditionSelect.value === 'any' ? 'all conditions' : 'new only';
  const freshness = formatGeneratedAt(payload.generated_at, payload.cached);
  const currencyLabel = payload.currency === 'NATIVE' ? 'native currencies' : payload.currency;
  statusLine.textContent = `Showing ${offers.length} offers in ${currencyLabel} (${conditionLabel}) — ${freshness}.`;

  offers.forEach((offer, index) => {
    const node = template.content.firstElementChild.cloneNode(true);
    node.querySelector('.product-name').textContent = formatProductName(offer.product);
    const convertedValue = offer.total.converted_value;
    const totalCurrency = offer.total.currency || offer.price.currency;
    node.querySelector('.converted-price').textContent = `${totalCurrency} ${convertedValue.toFixed(2)}`;
    node.querySelector('.original-price').textContent = `${offer.price.currency} ${offer.price.value.toFixed(2)} base price`;
    node.querySelector('.base-price').textContent = `Base: ${offer.price.currency} ${offer.price.converted_value.toFixed(2)}`;
    node.querySelector('.shipping').textContent = formatShipping(offer.shipping);
    node.querySelector('.merchant').textContent = `${offer.merchant.name} (${offer.merchant.country})`;
    node.querySelector('.timestamp').textContent = `Seen ${formatSeenAt(offer.seen_at)}`;
    const confidenceEl = node.querySelector('.confidence');
    confidenceEl.textContent = `Confidence: ${offer.confidence.toUpperCase()}`;
    if (offer.confidence_details) {
      confidenceEl.setAttribute('title', offer.confidence_details);
    } else {
      confidenceEl.removeAttribute('title');
    }
    node.querySelector('.availability').textContent = `Availability: ${offer.availability.replace('_', ' ')}`;
    node.querySelector('.condition').textContent = `Condition: ${offer.condition.toUpperCase()}`;
    node.querySelector('.open-link').href = offer.url;
    const analysisSummary = offer?.analysis?.summary ?? '';
    node.querySelector('.analysis-summary').textContent = analysisSummary;

    if (index === 0) {
      node.querySelector('.cheapest-badge').classList.remove('hidden');
    }

    const detailsButton = node.querySelector('.details-button');
    if (offer?.analysis?.cheapest) {
      detailsButton.textContent = 'Why cheapest?';
    } else {
      detailsButton.textContent = 'See breakdown';
    }
    detailsButton.addEventListener('click', () => openDetails(offer));

    resultsContainer.appendChild(node);
  });
}

function formatProductName(product) {
  const parts = [product.brand, product.name, product.variant].filter(Boolean);
  return parts.join(' – ');
}

function formatSeenAt(seenAt) {
  return relativeTimeFrom(seenAt);
}

function formatShipping(shipping) {
  const value = shipping.converted_value;
  const currency = shipping.currency || shipping.converted_currency || 'NATIVE';
  const label = value > 0 ? `${currency} ${value.toFixed(2)}` : 'Free';
  const hint = shipping.source === 'unknown' ? ' (est.)' : shipping.is_estimated ? ' (policy)' : '';
  return `Shipping: ${label}${hint}`;
}

function formatGeneratedAt(timestamp, cached) {
  const relative = relativeTimeFrom(timestamp);
  if (cached) {
    return `cached from ${relative}`;
  }
  return `updated ${relative}`;
}

function relativeTimeFrom(timestamp) {
  try {
    const date = new Date(timestamp);
    const diffMs = Date.now() - date.getTime();
    if (diffMs < 60_000) {
      return 'just now';
    }
    const diffMinutes = Math.round(diffMs / 60_000);
    if (diffMinutes < 60) {
      return `${diffMinutes} minutes ago`;
    }
    const diffHours = Math.round(diffMinutes / 60);
    if (diffHours < 24) {
      return `${diffHours} hours ago`;
    }
    return date.toLocaleString();
  } catch (error) {
    return timestamp;
  }
}

function openDetails(offer) {
  if (!offer) {
    return;
  }
  detailsTitle.textContent = formatProductName(offer.product);
  detailsSummary.textContent = offer?.analysis?.summary ?? 'No additional explanation available.';
  renderPriceBreakdown(offer.price_components ?? []);
  renderAssumptions(offer.assumptions ?? []);
  detailsConfidence.textContent = formatConfidenceDetails(offer);
  renderEvidence(offer.evidence ?? {});
  detailsLayer.classList.remove('hidden');
}

function closeDetails() {
  if (!detailsLayer.classList.contains('hidden')) {
    detailsLayer.classList.add('hidden');
  }
}

function renderPriceBreakdown(components) {
  detailsBreakdown.innerHTML = '';
  components.forEach((component) => {
    const li = document.createElement('li');
    const converted = `${component.converted_currency} ${component.converted_value.toFixed(2)}`;
    const original = `${component.currency} ${component.value.toFixed(2)}`;
    let suffix = '';
    if ('source' in component && component.source) {
      const origin = component.is_estimated ? 'estimated via' : 'provided by';
      suffix = ` — ${origin} ${component.source}`;
    }
    li.textContent = `${component.label}: ${converted} (${original})${suffix}`;
    detailsBreakdown.appendChild(li);
  });
}

function renderAssumptions(assumptions) {
  const list = Array.isArray(assumptions) ? assumptions.filter(Boolean) : [];
  detailsAssumptions.innerHTML = '';
  if (!list.length) {
    detailsAssumptionsSection.classList.add('hidden');
    return;
  }
  detailsAssumptionsSection.classList.remove('hidden');
  list.forEach((item) => {
    const li = document.createElement('li');
    li.textContent = item;
    detailsAssumptions.appendChild(li);
  });
}

function renderEvidence(evidence) {
  const snippet = evidence?.snippet ?? '';
  detailsEvidence.textContent = snippet || 'No saved snippet available for this offer yet.';
  const screenshot = evidence?.screenshot;
  if (screenshot) {
    detailsScreenshot.href = screenshot;
    detailsScreenshot.classList.remove('hidden');
  } else {
    detailsScreenshot.removeAttribute('href');
    detailsScreenshot.classList.add('hidden');
  }
}

function formatConfidenceDetails(offer) {
  const base = offer?.confidence?.toUpperCase() ?? 'UNKNOWN';
  if (!offer?.confidence_details) {
    return base;
  }
  return `${base} — ${offer.confidence_details}`;
}

searchButton.addEventListener('click', fetchOffers);
queryInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    fetchOffers();
  }
});
countrySelect.addEventListener('change', fetchOffers);
conditionSelect.addEventListener('change', fetchOffers);
detailsClose.addEventListener('click', closeDetails);
detailsLayer.addEventListener('click', (event) => {
  if (event.target === detailsLayer) {
    closeDetails();
  }
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && !detailsLayer.classList.contains('hidden')) {
    closeDetails();
  }
});
