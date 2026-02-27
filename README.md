# ScrapeClaw

Enterprise web scraper with Claude AI extraction and professional Excel output.

Crawl any website, extract structured data using Claude AI, and get a beautifully formatted Excel report — all from the command line.

## Quick Start

```bash
# Clone and install
git clone https://github.com/dariusX88/scrapeClaw.git
cd scrapeClaw
pip install -e .

# Add your Anthropic API key
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# Run the demo (scrapes books.toscrape.com)
scrapeclaw scrape example --max-pages 3
```

## Installation

### Option 1: One-line install (macOS/Linux)

```bash
curl -fsSL https://raw.githubusercontent.com/dariusX88/scrapeClaw/main/install.sh | bash
```

### Option 2: Manual install

```bash
git clone https://github.com/dariusX88/scrapeClaw.git
cd scrapeClaw
pip install -e .
```

### Option 3: Install directly from GitHub

```bash
pip install git+https://github.com/dariusX88/scrapeClaw.git
```

### Setup

After installing, add your API key:

```bash
cp .env.example .env
```

Edit `.env` and set `ANTHROPIC_API_KEY` to your key from [console.anthropic.com](https://console.anthropic.com/).

## Usage

### Scrape a site with a config

```bash
# Create a config for your target website
scrapeclaw init-config mysite https://example.com/listings

# Edit config/sites/mysite.yaml to define extraction fields
# Then scrape:
scrapeclaw scrape mysite
```

### Quick single-URL scrape

```bash
scrapeclaw scrape-url https://example.com -f "title,price,description"
```

### All commands

| Command | Description |
|---------|-------------|
| `scrapeclaw scrape <site>` | Crawl and extract data from a configured site |
| `scrapeclaw scrape-url <url>` | Scrape a single URL (no config needed) |
| `scrapeclaw init-config <name> <url>` | Generate a site config template |
| `scrapeclaw list-configs` | List available site configurations |
| `scrapeclaw list-results` | List recent output files |

### Scrape command options

```bash
scrapeclaw scrape <site> [OPTIONS]

Options:
  -u, --url TEXT          Override start URL
  -p, --max-pages INT     Max pages to crawl
  -n, --max-entries INT   Max entries to extract
  --playwright            Use Playwright for JS-heavy sites
  --no-claude             Skip AI extraction
  -o, --output TEXT       Output file path
  --dry-run               Crawl only, no extraction
  --json                  Also save data as JSON
```

## Site Configuration

Each site config is a YAML file in `config/sites/`. Example:

```yaml
name: mysite
base_url: https://example.com
start_url: https://example.com/products
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

The `extraction.fields` map tells Claude AI exactly what to extract from each page. Claude automatically handles both listing pages (returns multiple items) and detail pages (returns one item).

## Output

ScrapeClaw generates Excel reports with three worksheets:

- **Summary** — Run metadata, KPIs (success rate, tokens used)
- **Data** — All extracted records with styled headers, autofilter, clickable URLs
- **Charts** — Category distribution charts, field completeness stats

Output files are saved to `./output/` by default.

## Global Configuration

Edit `config/config.yaml` to change defaults:

```yaml
scraper:
  rate_limit:
    delay_sec: 1.5      # seconds between requests
    max_retries: 3       # retry failed requests
  proxy:
    enabled: false
    urls: []

claude:
  model: claude-sonnet-4-20250514    # or claude-haiku-4-5-20251001 for lower cost

output:
  dir: ./output
```

## Requirements

- Python 3.10+
- An [Anthropic API key](https://console.anthropic.com/) for Claude AI extraction
- Optional: [Playwright](https://playwright.dev/python/) for JavaScript-heavy sites

## License

MIT
