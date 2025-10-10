import requests
from bs4 import BeautifulSoup
import csv
import re
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import ttkbootstrap as tb

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
}

def parse_price(price_str):
    if not price_str:
        return None
    s = re.sub(r"[^\d\.]", "", price_str)
    try:
        return float(s)
    except:
        return None

def scrape_laptops_list(page_url, log_callback):
    resp = requests.get(page_url, headers=HEADERS)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    results = []
    product_cards = soup.select("div.product-card, li.product-item, div.grid-product")
    if not product_cards:
        product_cards = soup.find_all("h3")

    for pc in product_cards:
        try:
            name_tag = pc.find("a") or pc.find("h3")
            name = name_tag.get_text(strip=True) if name_tag else None
            link = name_tag["href"] if name_tag and name_tag.has_attr("href") else None
            if link and link.startswith("/"):
                link = "https://pcx.com.ph" + link

            price_el = pc.select_one(".price, .product-price, .money")
            price = price_el.get_text(strip=True) if price_el else None
            price_val = parse_price(price)

            results.append({
                "name": name,
                "link": link,
                "price_php": price_val,
            })
        except Exception as e:
            log_callback(f"Error parsing product card: {e}")
            continue

    return results

def scrape_spec_page(laptop, log_callback):
    if not laptop.get("link"):
        return {}
    try:
        resp = requests.get(laptop["link"], headers=HEADERS)
        resp.raise_for_status()
    except Exception as e:
        log_callback(f"Failed to fetch: {laptop['name']} ({e})")
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")
    specs = {}

    spec_section = None
    for h in soup.select("h4, h3, h2, strong"):
        if "Specification" in h.get_text():
            spec_section = h.find_parent()
            break
    if spec_section is None:
        spec_section = soup.select_one("div#ProductTabs-specification, div.product-specifications, div.tab-content")

    if spec_section:
        text = spec_section.get_text(separator="\n", strip=True)
        for line in text.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                specs[key.strip()] = val.strip()

    return specs

def merge_data(listings, log_callback):
    full = []
    for idx, l in enumerate(listings):
        log_callback(f"Scraping {idx+1}/{len(listings)}: {l.get('name')}")
        more = scrape_spec_page(l, log_callback)
        merged = {**l, **more}
        full.append(merged)
        time.sleep(0.5)
    return full

def write_csv(data, out_filename="laptops_scraped.csv"):
    keys = set()
    for d in data:
        keys.update(d.keys())
    keys = sorted(keys)

    with open(out_filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for d in data:
            writer.writerow(d)

class ScraperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("PCX Specification Scraper")
        self.root.geometry("780x480")
        self.root.resizable(False, False)

        # Frame container (green rounded background)
        self.container = tk.Frame(root, bg="#4b8253", bd=5, relief="flat")
        self.container.place(relx=0.5, rely=0.5, anchor="center", width=740, height=440)

        # Title
        tk.Label(
            self.container, 
            text="Insert link", 
            bg="#4b8253", 
            fg="black", 
            font=("Segoe UI", 12, "bold")
        ).place(x=130, y=60)

        # Input field
        self.url_entry = ttk.Entry(self.container, width=50)
        self.url_entry.place(x=250, y=60)
        self.url_entry.insert(0, "https://pcx.com.ph/collections/laptops")

        # Start button
        self.start_button = tb.Button(self.container, text="Start", bootstyle="success", command=self.start_scraping)
        self.start_button.place(relx=0.5, y=110, anchor="center")

        # Log box (large gray area)
        self.log_box = tk.Text(
            self.container, 
            height=12, 
            width=80, 
            wrap="word", 
            bg="#d9d9d9", 
            relief="flat", 
            font=("Segoe UI", 10)
        )
        self.log_box.place(x=60, y=150)

        # Progress bar
        self.progress = ttk.Progressbar(self.container, mode="indeterminate")
        self.progress.place(x=60, y=370, width=620)

    def log(self, message):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.configure(state="disabled")
        self.log_box.see("end")
        self.root.update_idletasks()

    def start_scraping(self):
        url = self.url_entry.get().strip()
        if not url.startswith("http"):
            messagebox.showerror("Invalid URL", "Please enter a valid PCX URL.")
            return

        self.start_button.config(state="disabled")
        self.progress.start()
        self.log(f"Starting scraping for: {url}")

        thread = threading.Thread(target=self.run_scraper, args=(url,))
        thread.start()

    def run_scraper(self, url):
        try:
            listings = scrape_laptops_list(url, self.log)
            self.log(f"Found {len(listings)} product listings.")
            if not listings:
                raise ValueError("No products found on this page.")
            full_data = merge_data(listings, self.log)
            write_csv(full_data)
            self.log("✅ Done! CSV saved as 'laptops_scraped.csv'")
            messagebox.showinfo("Success", "Scraping complete! CSV saved.")
        except Exception as e:
            self.log(f"❌ Error: {e}")
            messagebox.showerror("Error", str(e))
        finally:
            self.progress.stop()
            self.start_button.config(state="normal")

if __name__ == "__main__":
    app = tb.Window(themename="flatly")  # "flatly" gives a clean green-gray modern theme
    ScraperGUI(app)
    app.mainloop()
