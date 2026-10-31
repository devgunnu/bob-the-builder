---
source_url: https://docs.firecrawl.dev/features/map
title: Map | Firecrawl
fetched_at: 2026-10-31T02:34:21+00:00
---

## Introducing /map

The easiest way to go from a single url to a map of the entire website. This is extremely useful for:

- When you need to prompt the end-user to choose which links to scrape
- Need to quickly know the links on a website
- Need to scrape pages of a website that are related to a specific topic (use the `search` parameter)
- Only need to scrape specific pages of a website

[**Try it in the Playground** \\
\\
Test mapping in the interactive playground — no code required.](https://www.firecrawl.dev/playground?endpoint=map)

## Mapping

### /map endpoint

Used to map a URL and get urls of the website. This returns most links present on the website.URLs are primarily discovered from the website’s sitemap, supplemented with SERP (search engine) results and previously crawled pages to improve coverage. You can control sitemap behavior with the `sitemap` parameter.

### Installation

Python

Node

CLI

```
# pip install firecrawl

from firecrawl import Firecrawl

firecrawl = Firecrawl(
  # No API key needed to get started — add one for higher rate limits:
  # api_key="fc-YOUR-API-KEY",
)
```

```
// npm install firecrawl

import { Firecrawl } from 'firecrawl';

const firecrawl = new Firecrawl({
  // No API key needed to get started — add one for higher rate limits:
  // apiKey: "fc-YOUR-API-KEY",
});
```

```
# Install globally with npm
npm install -g firecrawl

# Authenticate (one-time setup)
firecrawl login
```

### Usage

Python

Node

cURL

CLI

```
from firecrawl import Firecrawl

firecrawl = Firecrawl(api_key="fc-YOUR-API-KEY")
res = firecrawl.map(url="https://firecrawl.dev", limit=50, sitemap="include")
print(res)
```

```
import { Firecrawl } from 'firecrawl';

const firecrawl = new Firecrawl({ apiKey: "fc-YOUR-API-KEY" });

const res = await firecrawl.map('https://firecrawl.dev', { limit: 50, sitemap: 'include' });
console.log(res);
```

```
curl -X POST https://api.firecrawl.dev/v2/map \
    -H 'Content-Type: application/json' \
    -H 'Authorization: Bearer YOUR_API_KEY' \
    -d '{
      "url": "https://firecrawl.dev"
    }'
```

```
# Map a website to discover URLs
firecrawl map https://firecrawl.dev

# Output as JSON with limit
firecrawl map https://firecrawl.dev --json --limit 100 --pretty
```

Each map request consumes 1 credit per call, regardless of the number of URLs returned. For example, setting `limit` to 100,000 still uses 1 credit.

### Response

SDKs will return the data object directly. cURL will return the payload exactly as shown below.

```
{
  "success": true,
  "links": [\
    {\
      "url": "https://docs.firecrawl.dev/features/scrape",\
      "title": "Scrape | Firecrawl",\
      "description": "Turn any url into clean data"\
    },\
    {\
      "url": "https://www.firecrawl.dev/blog/5_easy_ways_to_access_glm_4_5",\
      "title": "5 Easy Ways to Access GLM-4.5",\
      "description": "Discover how to access GLM-4.5 models locally, through chat applications, via the official API, and using the LLM marketplaces API for seamless integration i..."\
    },\
    {\
      "url": "https://www.firecrawl.dev/playground",\
      "title": "Playground - Firecrawl",\
      "description": "Preview the API response and get the code snippets for the API"\
    },\
    {\
      "url": "https://www.firecrawl.dev/?testId=2a7e0542-077b-4eff-bec7-0130395570d6",\
      "title": "Firecrawl - The Web Data API for AI",\
      "description": "The web crawling, scraping, and search API for AI. Built for scale. Firecrawl delivers the entire internet to AI agents and builders. Clean, structured, and ..."\
    },\
    {\
      "url": "https://www.firecrawl.dev/?testId=af391f07-ca0e-40d3-8ff2-b1ecf2e3fcde",\
      "title": "Firecrawl - The Web Data API for AI",\
      "description": "The web crawling, scraping, and search API for AI. Built for scale. Firecrawl delivers the entire internet to AI agents and builders. Clean, structured, and ..."\
    },\
    ...\
  ]
}
```

Title and description are not always present as it depends on the website.

#### Map with search

Map with `search` param allows you to search for specific urls inside a website.

cURL

```
curl -X POST https://api.firecrawl.dev/v2/map \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_API_KEY' \
  -d '{
    "url": "https://firecrawl.dev",
    "search": "docs"
  }'
```

Response will be an ordered list from the most relevant to the least relevant.

```
{
  "status": "success",
  "links": [\
    {\
      "url": "https://docs.firecrawl.dev",\
      "title": "Firecrawl Docs",\
      "description": "Firecrawl documentation"\
    },\
    {\
      "url": "https://docs.firecrawl.dev/sdks/python",\
      "title": "Firecrawl Python SDK",\
      "description": "Firecrawl Python SDK documentation"\
    },\
    ...\
  ]
}
```

## Location and Language

Specify country and preferred languages to get relevant content based on your target location and language preferences, similar to the scrape endpoint.

### How it works

When you specify the location settings, Firecrawl will use an appropriate proxy if available and emulate the corresponding language and timezone settings. By default, the location is set to ‘US’ if not specified.

### Usage

To use the location and language settings, include the `location` object in your request body with the following properties:

- `country`: ISO 3166-1 alpha-2 country code (e.g., ‘US’, ‘AU’, ‘DE’, ‘JP’). Defaults to ‘US’.
- `languages`: An array of preferred languages and locales for the request in order of priority. Defaults to the language of the specified location.

Python

Node

cURL

```
from firecrawl import Firecrawl

firecrawl = Firecrawl(api_key="fc-YOUR-API-KEY")

res = firecrawl.map('https://example.com',
    location={
        'country': 'US',
        'languages': ['en']
    }
)

print(res)
```

```
import { Firecrawl } from 'firecrawl';

const firecrawl = new Firecrawl({ apiKey: "fc-YOUR-API-KEY" });

const res = await firecrawl.map('https://example.com', {
  location: { country: 'US', languages: ['en'] },
});

console.log(res.metadata);
```

```
curl -X POST "https://api.firecrawl.dev/v2/map" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "location": { "country": "US", "languages": ["en"] }
  }'
```

For more details about supported locations, refer to the [Proxies documentation](https://docs.firecrawl.dev/features/proxies).

## Considerations

This endpoint prioritizes speed, so it may not capture all website links. It primarily relies on the website’s sitemap, supplemented by cached crawl data and search engine results. For a more thorough and up-to-date list of URLs, consider using the [/crawl](https://docs.firecrawl.dev/features/crawl) endpoint instead.If you need more thorough recursive discovery with auditable result and error records rather than a fast approximation, use [/crawl](https://docs.firecrawl.dev/features/crawl), which discovers pages by recursive link traversal as well as the sitemap and reports what it returned and what it failed to fetch — see [Execution and result accounting](https://docs.firecrawl.dev/features/crawl#execution-and-result-accounting). For the links on one specific page, request the [`links` format](https://docs.firecrawl.dev/features/scrape#scrape-formats) from [/scrape](https://docs.firecrawl.dev/features/scrape).

> Are you an AI agent that needs a Firecrawl API key? See [firecrawl.dev/agent-onboarding/SKILL.md](https://www.firecrawl.dev/agent-onboarding/SKILL.md) for automated onboarding instructions.
