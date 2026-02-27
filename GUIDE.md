# ScrapeClaw — How to Use Guide

## Table of Contents

1. [Installation](#installation)
2. [Setup Your API Key](#setup-your-api-key)
3. [Your First Scrape (Demo)](#your-first-scrape-demo)
4. [Scrape Any URL (No Config Needed)](#scrape-any-url-no-config-needed)
5. [Create a Config for a New Website](#create-a-config-for-a-new-website)
6. [Site Config Explained](#site-config-explained)
7. [Understanding the Excel Output](#understanding-the-excel-output)
8. [Command Reference](#command-reference)
9. [Advanced Options](#advanced-options)
10. [Global Configuration](#global-configuration)
11. [Troubleshooting](#troubleshooting)

---

## Installation

### Quick install (macOS / Linux)

```bash
curl -fsSL https://raw.githubusercontent.com/dariusX88/scrapeClaw/main/install.sh | bash
```

### Manual install

```bash
git clone https://github.com/dariusX88/scrapeClaw.git
cd scrapeClaw
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

After installing, activate the virtual environment whenever you use ScrapeClaw:

```bash
cd scrapeClaw
source .venv/bin/activate
```

Or run commands directly without activating:

```bash
.venv/bin/scrapeclaw <command>
```

---

## Setup Your API Key

ScrapeClaw uses Claude AI to intelligently extract data from web pages. You need an Anthropic API key.

1. Get your key from [console.anthropic.com](https://console.anthropic.com/)
2. Copy the example env file and add your key:

```bash
cp .env.example .env
```

3. Open `.env` in any text editor and replace the placeholder:

```
ANTHROPIC_API_KEY=sk-ant-api03-your-actual-key-here
```

---

## Your First Scrape (Demo)

ScrapeClaw ships with a demo config that scrapes [books.toscrape.com](https://books.toscrape.com), a safe practice site.

```bash
scrapeclaw scrape example --max-pages 3
```

This will:
1. Crawl up to 3 pages of the book catalog
2. Send each page to Claude AI to extract: title, price, rating, availability, and URL
3. Generate a styled Excel report in `./output/`

You should see output like:

```
╭─ ScrapeClaw — Enterprise Web Scraper ─╮
│ AI-powered extraction with beautiful   │
│ Excel output                           │
╰────────────────────────────────────────╯
  Target: https://books.toscrape.com/catalogue/page-1.html
  Max pages: 3 | Max entries: 50

  Crawling...  5/3 pages (BFS may find extras)

  Extracting with Claude...  5/5 pages
  Extraction complete: 20 records from 5 pages, 12,345 tokens used

  Done! Excel report: output/example_20260227_140000.xlsx
```

### Try a dry run first

If you just want to see what gets crawled without using Claude (free, no API cost):

```bash
scrapeclaw scrape example --max-pages 3 --dry-run
```

---

## Scrape Any URL (No Config Needed)

For quick one-off scrapes, use `scrape-url` — no config file required:

```bash
# Extract specific fields from a page
scrapeclaw scrape-url https://example.com/products -f "title,price,description"

# Scrape without Claude (just grabs title/description metadata)
scrapeclaw scrape-url https://example.com --no-claude
```

The `-f` / `--fields` flag tells Claude what to extract. Use comma-separated field names that describe the data you want. Claude is smart enough to understand what you mean:

```bash
# E-commerce product page
scrapeclaw scrape-url https://shop.example.com/item -f "name,price,rating,reviews_count"

# Job listing
scrapeclaw scrape-url https://jobs.example.com/posting -f "job_title,company,salary,location,requirements"

# Real estate listing
scrapeclaw scrape-url https://realty.example.com/house -f "address,price,bedrooms,bathrooms,square_feet"
```

---

## Create a Config for a New Website

For websites you want to scrape regularly or need to crawl multiple pages, create a site config:

### Step 1: Generate the template

```bash
scrapeclaw init-config mysite https://example.com/listings
```

This creates `config/sites/mysite.yaml`.

### Step 2: Edit the config

Open `config/sites/mysite.yaml` and customize:

```yaml
name: mysite
base_url: https://example.com
start_url: https://example.com/listings
allowed_domains:
  - example.com
max_pages: 30
max_entries: 200

rate_limit:
  delay_sec: 2.0

extraction:
  fields:
    title: "Product or listing title"
    price: "Price as a number, no currency symbol"
    description: "Short description, max 200 chars"
    category: "Product category"
    url: "Direct link to the item"
```

The key part is `extraction.fields` — each entry is:
- **Key**: the column name that appears in your Excel output
- **Value**: a plain-English description telling Claude what to look for

### Step 3: Run the scrape

```bash
scrapeclaw scrape mysite
```

### Step 4: Check your results

```bash
scrapeclaw list-results
```

---

## Site Config Explained

Here's what each field in a site config does:

```yaml
# Identification
name: mysite                    # Name used in CLI commands
base_url: https://example.com   # Base URL for resolving relative links

# Crawling
start_url: https://example.com/page-1   # Where the crawler starts
allowed_domains:                         # Only follow links to these domains
  - example.com
max_pages: 30          # Stop crawling after this many pages
max_entries: 200       # Stop extracting after this many items
js_required: false     # Set true for JavaScript-heavy sites (needs Playwright)

# Politeness
rate_limit:
  delay_sec: 2.0       # Wait N seconds between requests (be respectful)

# Optional: CSS selectors (for non-Claude extraction)
css_selectors:
  title: h3 a
  price: .price_color

# Optional: extra headers
custom_headers:
  Accept-Language: en-US,en;q=0.9

# Claude AI extraction
extraction:
  fields:
    title: "The item's title"              # What to extract and how
    price: "Price as number, no currency"
    url: "Direct link to the item"
  max_tokens: 2048     # Max tokens for Claude's response (increase for complex pages)
```

### How the crawler works

ScrapeClaw uses breadth-first search (BFS):

1. Starts at `start_url`
2. Fetches the page, extracts all links
3. Filters links to `allowed_domains` only
4. Adds new links to the queue (skips already-visited URLs)
5. Repeats until `max_pages` is reached or no more links to follow

### How Claude extraction works

For each crawled page, ScrapeClaw sends the page text to Claude with your field descriptions. Claude is smart about page types:

- **Listing pages** (product grids, search results): Claude returns multiple items per page
- **Detail pages** (single product, single article): Claude returns one item

You don't need to tell it which type — it figures it out automatically.

---

## Understanding the Excel Output

Each scrape generates an Excel file with 3 worksheets:

### Summary sheet

- Run date and configuration used
- Total records extracted
- Success rate (% of pages that yielded data)
- Total Claude API tokens consumed
- Key run parameters

### Data sheet

- One row per extracted item
- Styled headers with autofilter (click headers to sort/filter)
- Alternating row colors for readability
- Clickable URL hyperlinks
- Error rows highlighted in red
- Frozen header row (stays visible while scrolling)

### Charts sheet

- Category distribution bar chart (if items have categories)
- Field completeness stats showing which fields were found most often

Output files are saved to `./output/` by default.

---

## Command Reference

### `scrapeclaw scrape <site>`

Crawl and extract data from a configured site.

```bash
scrapeclaw scrape example                     # Use all defaults from config
scrapeclaw scrape example --max-pages 5       # Override max pages
scrapeclaw scrape example --max-entries 100   # Override max entries
scrapeclaw scrape example --dry-run           # Crawl only, no Claude, no Excel
scrapeclaw scrape example --no-claude         # Crawl + Excel, but skip Claude AI
scrapeclaw scrape example --json              # Also save data as JSON
scrapeclaw scrape example --playwright        # Use browser rendering (JS sites)
scrapeclaw scrape example -o report.xlsx      # Custom output path
scrapeclaw scrape example -u https://other.com/page  # Override start URL
```

| Flag | Short | Description |
|------|-------|-------------|
| `--url` | `-u` | Override the start URL from the config |
| `--max-pages` | `-p` | Max pages to crawl |
| `--max-entries` | `-n` | Max items to extract |
| `--playwright` | | Use Playwright for JS-heavy sites |
| `--no-claude` | | Skip AI extraction, just grab basic metadata |
| `--output` | `-o` | Custom output file path |
| `--dry-run` | | Crawl only — no extraction, no output file |
| `--json` | | Also save results as a `.json` file |

### `scrapeclaw scrape-url <url>`

Scrape a single URL without any config file.

```bash
scrapeclaw scrape-url https://example.com -f "title,price,description"
scrapeclaw scrape-url https://example.com --no-claude
scrapeclaw scrape-url https://example.com -f "name,email" -o contacts.xlsx
```

| Flag | Short | Description |
|------|-------|-------------|
| `--fields` | `-f` | Comma-separated fields to extract |
| `--no-claude` | | Skip AI, just grab page metadata |
| `--output` | `-o` | Custom output file path |

### `scrapeclaw init-config <name> <url>`

Generate a new site config template.

```bash
scrapeclaw init-config shopify https://mystore.com/collections/all
```

### `scrapeclaw list-configs`

Show all available site configurations.

```bash
scrapeclaw list-configs
```

### `scrapeclaw list-results`

Show recent output files with size and date.

```bash
scrapeclaw list-results           # Show last 20 files
scrapeclaw list-results -n 50     # Show last 50 files
```

---

## Advanced Options

### JavaScript-heavy websites

Some websites load content with JavaScript (React, Angular, SPAs). The default HTTP fetcher won't see this content. Use Playwright:

```bash
# Install Playwright support
pip install playwright
playwright install chromium

# Scrape with browser rendering
scrapeclaw scrape mysite --playwright
```

Or set `js_required: true` in your site config to always use Playwright for that site.

### Proxy support

Edit `config/config.yaml`:

```yaml
scraper:
  proxy:
    enabled: true
    urls:
      - http://proxy1.example.com:8080
      - http://proxy2.example.com:8080
```

### Rate limiting

Be respectful to websites. Adjust the delay between requests:

```yaml
# In your site config
rate_limit:
  delay_sec: 3.0     # Wait 3 seconds between requests
```

Or in the global config to set a default for all sites:

```yaml
# config/config.yaml
scraper:
  rate_limit:
    delay_sec: 2.0
    max_retries: 3
```

### JSON output

Get results as JSON alongside Excel:

```bash
scrapeclaw scrape example --json
```

This creates both `output/example_20260227.xlsx` and `output/example_20260227.json`.

### Change the Claude model

Edit `config/config.yaml`:

```yaml
claude:
  model: claude-haiku-4-5-20251001    # Faster and cheaper
  # model: claude-sonnet-4-20250514   # Default — best balance
```

---

## Global Configuration

The file `config/config.yaml` controls defaults for all scrapes:

```yaml
scraper:
  rate_limit:
    delay_sec: 1.5       # Seconds between requests
    max_retries: 3        # Retry failed requests this many times
    retry_wait_min: 1.0   # Min wait between retries
    retry_wait_max: 5.0   # Max wait between retries
  proxy:
    enabled: false
    urls: []

claude:
  model: claude-sonnet-4-20250514
  max_tokens: 4096

output:
  dir: ./output
  excel_theme:
    header_color: "1A3A5C"       # Dark blue headers
    header_font_color: "FFFFFF"  # White header text
    alt_row_color: "EBF2FA"      # Light blue alternating rows
    accent_color: "2980B9"       # Blue accents
    border_color: "B0C4D8"       # Light border

logging:
  level: INFO    # DEBUG for verbose output
```

### Environment variable overrides

These env vars (set in `.env` or your shell) override config file values:

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | **Required.** Your Claude API key |
| `SCRAPECLAW_OUTPUT_DIR` | Override output directory |
| `SCRAPECLAW_LOG_LEVEL` | Override log level (DEBUG, INFO, WARNING, ERROR) |

---

## Troubleshooting

### "ANTHROPIC_API_KEY not set"

Make sure your `.env` file exists and contains your key:

```bash
cp .env.example .env
nano .env   # or any text editor
```

Add: `ANTHROPIC_API_KEY=sk-ant-api03-your-key-here`

### Claude returns empty/null fields

- The page might load content via JavaScript. Try `--playwright`.
- The page might be very large. Claude works with the first ~12,000 characters of text.
- Try being more specific in your field descriptions: instead of `"price"`, use `"Price as a number without currency symbol"`.

### "externally-managed-environment" error

Your system Python is managed by Homebrew/apt. Use the virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Scraper gets blocked / 403 errors

- Increase `rate_limit.delay_sec` to be more polite (3-5 seconds).
- Some sites block automated requests. Try adding custom headers in your site config.
- Use `--playwright` for a more browser-like request.

### Excel file won't open

Make sure `openpyxl` is installed (it should be if you ran `pip install -e .`). The output is `.xlsx` format compatible with Excel, Google Sheets, and Numbers.

### Logs

Check the `logs/` directory for detailed logs:

```bash
ls logs/
cat logs/scrapeclaw_20260227.log
```

Set `SCRAPECLAW_LOG_LEVEL=DEBUG` in `.env` for verbose output.
