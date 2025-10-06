import requests
from bs4 import BeautifulSoup
import csv
import re
import time

BASE_URL = "https://pcx.com.ph"
LAPTOPS_LIST_URL = "https://pcx.com.ph/collections/laptops"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
                  "(KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
}

def parse_price(price_str):
    """
    Parse price string like “₱26,999.00” into float (in PHP) or integer.
    """
    if not price_str:
        return None
    # remove non-digits and commas
    s = re.sub(r"[^\d\.]", "", price_str)
    try:
        return float(s)
    except:
        return None

def scrape_laptops_list(page_url):
    """
    Scrape the listing page to get each laptop’s name, link, price, and quick spec snippet.
    Returns a list of dicts.
    """
    resp = requests.get(page_url, headers=HEADERS)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    results = []
    # Each product is in something like an “###” heading, then price etc.
    # Let’s look for product containers; from HTML, product name is in <h3> or “###” marker in the source.
    # For example: <h3>ACER Aspire A514-55-330C Intel® Core™ i3 Laptop …</h3>
    product_cards = soup.select("div.product-card, li.product-item, div.grid-product")
    # Fallback: try elements containing “###” text
    if not product_cards:
        # Try scanning h3 tags that begin with “###” (from page source)
        product_cards = soup.find_all("h3")

    for pc in product_cards:
        try:
            # find name
            name_tag = pc.find("a") or pc.find("h3")
            name = name_tag.get_text(strip=True) if name_tag else None

            # link
            link = name_tag["href"] if name_tag and name_tag.has_attr("href") else None
            if link and link.startswith("/"):
                link = BASE_URL + link

            # price (look for sibling or child price elements)
            price = None
            price_el = pc.select_one(".price, .product-price, .money")
            if price_el:
                price = price_el.get_text(strip=True)
            else:
                # maybe sibling
                sib = pc.find_next_sibling(text=re.compile(r"₱"))
                if sib:
                    price = sib.strip()

            price_val = parse_price(price)

            # quick spec snippet: sometimes appears after listing
            snippet = ""
            # e.g. in “SPECIFICATION Operating System …” text in the listing
            spec_div = pc.find_next(string=re.compile(r"SPECIFICATION", re.IGNORECASE))
            if spec_div:
                snippet = spec_div.strip()

            results.append({
                "name": name,
                "link": link,
                "price_php": price_val,
                "quick_spec": snippet
            })
        except Exception as e:
            print("Error parsing product card:", e)
            continue

    return results

def scrape_spec_page(laptop):
    """
    Given a laptop dict with a “link”, try to fetch the detail page and extract more specs.
    Returns a dict of new fields.
    """
    if not laptop.get("link"):
        return {}
    try:
        resp = requests.get(laptop["link"], headers=HEADERS)
        resp.raise_for_status()
    except Exception as e:
        print("Failed to fetch detail page:", laptop["link"], e)
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")
    specs = {}

    # For example, the “SPECIFICATION” section might be in a <div> or <table>
    # Let's find a section / div which contains “SPECIFICATION” in heading
    spec_section = None
    for h in soup.select("h4, h3, h2, strong"):
        if "Specification" in h.get_text():
            # likely the next sibling or parent is the block with details
            spec_section = h.find_parent()
            break

    # If not found, try to find <div> or <section> with class “tab-content” or “product-spec”
    if spec_section is None:
        spec_section = soup.select_one("div#ProductTabs-specification, div.product-specifications, div.tab-content")

    if spec_section:
        # get all lines of specs
        text = spec_section.get_text(separator="\n", strip=True)
        # We can parse lines like “Processor: Intel i7-1255U” etc.
        for line in text.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                key = key.strip()
                val = val.strip()
                specs[key] = val

    # Also get weight, battery if present elsewhere
    # eg: class “weight” or “Battery”
    battery_el = soup.find(text=re.compile(r"Battery", re.IGNORECASE))
    if battery_el:
        specs["Battery"] = battery_el.strip()

    weight_el = soup.find(text=re.compile(r"Weight", re.IGNORECASE))
    if weight_el:
        specs["Weight"] = weight_el.strip()

    return specs

def merge_data(listings):
    """
    For each listing, fetch detail specs and merge.
    """
    full = []
    for idx, l in enumerate(listings):
        print(f"Scraping {idx+1}/{len(listings)}: {l.get('name')}")
        more = scrape_spec_page(l)
        merged = {**l, **more}
        full.append(merged)
        time.sleep(0.5)  # be polite
    return full

def write_csv(data, out_filename="laptops_scraped.csv"):
    # Gather all keys
    keys = set()
    for d in data:
        keys.update(d.keys())
    keys = sorted(keys)

    with open(out_filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for d in data:
            writer.writerow(d)

def main():
    listings = scrape_laptops_list(LAPTOPS_LIST_URL)
    print(f"Found {len(listings)} laptop listings.")
    full_data = merge_data(listings)
    write_csv(full_data)
    print("Done. CSV saved.")

if __name__ == "__main__":
    main()
