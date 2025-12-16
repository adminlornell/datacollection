#!/usr/bin/env python3
"""
HTTP-based scraper for Wachusett St using requests + BeautifulSoup.
Handles ASP.NET viewstate and session management.
"""
import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime
from urllib.parse import urljoin, parse_qs, urlparse
import time

BASE_URL = "https://gis.vgsi.com/worcesterma"
STREET_NAME = "WACHUSETT ST"

# Mimic a real browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}


def get_aspnet_fields(soup):
    """Extract ASP.NET hidden fields for postback."""
    fields = {}
    for field in ['__VIEWSTATE', '__VIEWSTATEGENERATOR', '__EVENTVALIDATION', '__EVENTTARGET', '__EVENTARGUMENT']:
        element = soup.find('input', {'name': field})
        if element:
            fields[field] = element.get('value', '')
    return fields


def scrape_wachusett_street():
    """Scrape all properties on Wachusett St using HTTP requests."""

    print(f"Starting HTTP scrape for: {STREET_NAME}")
    print("=" * 60)

    session = requests.Session()
    session.headers.update(HEADERS)

    # Step 1: Get the Streets page
    print("\n[1] Fetching Streets.aspx...")
    try:
        response = session.get(f"{BASE_URL}/Streets.aspx", timeout=30)
        print(f"    Status: {response.status_code}")

        if response.status_code != 200:
            print(f"    Failed to access Streets page: {response.status_code}")
            return None

    except Exception as e:
        print(f"    Error: {e}")
        return None

    soup = BeautifulSoup(response.text, 'lxml')

    # Save the page for debugging
    with open('/home/user/datacollection/debug_streets.html', 'w') as f:
        f.write(response.text)
    print("    Saved debug HTML: debug_streets.html")

    # Step 2: Find streets and look for Wachusett St link
    print("\n[2] Looking for street links...")

    # Find all links that might be streets
    all_links = soup.find_all('a')
    street_links = []
    wachusett_link = None

    for link in all_links:
        href = link.get('href', '')
        text = link.get_text(strip=True)

        if 'Results.aspx' in href or 'Street=' in href:
            street_links.append({'text': text, 'href': href})
            if 'WACHUSETT' in text.upper():
                wachusett_link = {'text': text, 'href': href}
                print(f"    Found Wachusett St link: {text} -> {href}")

    print(f"    Total street links found: {len(street_links)}")

    # If no direct link, check if there's alphabetical navigation
    if not wachusett_link:
        print("\n    Looking for alphabetical navigation...")
        letter_links = soup.find_all('a', href=re.compile(r'letter=W', re.I))
        if letter_links:
            print(f"    Found letter 'W' link: {letter_links[0].get('href')}")

            # Navigate to W streets
            w_url = urljoin(BASE_URL + '/', letter_links[0].get('href'))
            response = session.get(w_url, timeout=30)
            soup = BeautifulSoup(response.text, 'lxml')

            # Look again for Wachusett
            for link in soup.find_all('a'):
                text = link.get_text(strip=True)
                href = link.get('href', '')
                if 'WACHUSETT' in text.upper():
                    wachusett_link = {'text': text, 'href': href}
                    print(f"    Found Wachusett St link: {text}")
                    break

    # Show first few street links for debugging
    print("\n    Sample street links found:")
    for sl in street_links[:10]:
        print(f"      - {sl['text']}: {sl['href']}")

    if not wachusett_link and street_links:
        # Check if Wachusett is in the list
        for sl in street_links:
            if 'WACHUSETT' in sl['text'].upper():
                wachusett_link = sl
                break

    if not wachusett_link:
        print("\n    Could not find Wachusett St directly.")
        print("    Listing all 'W' streets...")
        w_streets = [sl for sl in street_links if sl['text'].upper().startswith('W')]
        for ws in w_streets:
            print(f"      - {ws['text']}")

        # Try search functionality if available
        print("\n    Trying search functionality...")
        search_url = f"{BASE_URL}/Search.aspx"
        try:
            search_response = session.get(search_url, timeout=30)
            if search_response.status_code == 200:
                with open('/home/user/datacollection/debug_search.html', 'w') as f:
                    f.write(search_response.text)
                print("    Search page found - saved to debug_search.html")
        except:
            pass

        return None

    # Step 3: Navigate to the street's property listing
    print(f"\n[3] Navigating to {wachusett_link['text']} property listing...")

    street_url = urljoin(BASE_URL + '/', wachusett_link['href'])
    response = session.get(street_url, timeout=30)

    if response.status_code != 200:
        print(f"    Failed: {response.status_code}")
        return None

    with open('/home/user/datacollection/debug_wachusett_properties.html', 'w') as f:
        f.write(response.text)
    print("    Saved: debug_wachusett_properties.html")

    soup = BeautifulSoup(response.text, 'lxml')

    # Step 4: Extract property links
    print("\n[4] Extracting property links...")

    property_links = []

    # Look for links to Parcel.aspx
    parcel_links = soup.find_all('a', href=re.compile(r'Parcel\.aspx', re.I))

    for link in parcel_links:
        href = link.get('href', '')
        text = link.get_text(strip=True)

        # Extract PID from URL
        parsed = urlparse(href)
        params = parse_qs(parsed.query)
        pid = params.get('pid', params.get('PID', ['']))[0]

        if pid:
            property_links.append({
                'address': text,
                'pid': pid,
                'url': urljoin(BASE_URL + '/', href)
            })

    print(f"    Found {len(property_links)} properties")

    if not property_links:
        # Try finding properties in tables
        print("    Trying table-based extraction...")
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                for cell in cells:
                    link = cell.find('a', href=re.compile(r'Parcel|pid', re.I))
                    if link:
                        href = link.get('href', '')
                        text = link.get_text(strip=True)
                        parsed = urlparse(href)
                        params = parse_qs(parsed.query)
                        pid = params.get('pid', params.get('PID', ['']))[0]
                        if pid and pid not in [p['pid'] for p in property_links]:
                            property_links.append({
                                'address': text,
                                'pid': pid,
                                'url': urljoin(BASE_URL + '/', href)
                            })

        print(f"    After table scan: {len(property_links)} properties")

    # Step 5: Scrape details for each property (limit to 5 for demo)
    print("\n[5] Scraping property details...")

    properties = []

    for idx, prop_info in enumerate(property_links[:5], 1):
        print(f"\n    [{idx}/{min(5, len(property_links))}] {prop_info['address']} (PID: {prop_info['pid']})")
        time.sleep(1)  # Be respectful

        try:
            response = session.get(prop_info['url'], timeout=30)

            if response.status_code != 200:
                print(f"        Failed: HTTP {response.status_code}")
                continue

            soup = BeautifulSoup(response.text, 'lxml')

            # Save first property page for debugging
            if idx == 1:
                with open('/home/user/datacollection/debug_property_detail.html', 'w') as f:
                    f.write(response.text)
                print("        Saved debug: debug_property_detail.html")

            property_data = {
                'parcel_id': prop_info['pid'],
                'address': prop_info['address'],
                'url': prop_info['url'],
                'scraped_at': datetime.now().isoformat(),
            }

            # Extract data using various patterns
            # Pattern 1: Look for labeled spans (common in VGSI)
            for span in soup.find_all('span', id=True):
                span_id = span.get('id', '').lower()
                text = span.get_text(strip=True)

                if text:
                    if 'owner' in span_id:
                        property_data['owner'] = text
                    elif 'location' in span_id:
                        property_data['location'] = text
                    elif 'coowner' in span_id:
                        property_data['co_owner'] = text
                    elif 'mailingaddress' in span_id or 'address' in span_id:
                        if 'mailing_address' not in property_data:
                            property_data['mailing_address'] = text

            # Pattern 2: Extract from tables
            details = {}
            tables = soup.find_all('table')

            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True).rstrip(':')
                        value = cells[1].get_text(strip=True)

                        if label and value and len(label) < 50 and label != value:
                            details[label] = value

            property_data['details'] = details

            # Extract images
            photos = []
            for img in soup.find_all('img', src=True):
                src = img.get('src', '')
                img_id = img.get('id', '').lower()

                if any(x in src.lower() or x in img_id for x in ['photo', 'image', 'getimage']):
                    if 'placeholder' not in src.lower() and 'blank' not in src.lower():
                        full_url = urljoin(prop_info['url'], src)
                        photos.append(full_url)

            property_data['photos'] = list(set(photos))

            # Extract sketches/layouts
            layouts = []
            for img in soup.find_all('img', src=True):
                src = img.get('src', '')
                img_id = img.get('id', '').lower()

                if any(x in src.lower() or x in img_id for x in ['sketch', 'layout', 'floor']):
                    full_url = urljoin(prop_info['url'], src)
                    layouts.append(full_url)

            property_data['layouts'] = list(set(layouts))

            properties.append(property_data)

            print(f"        Owner: {property_data.get('owner', 'N/A')}")
            print(f"        Location: {property_data.get('location', 'N/A')}")
            print(f"        Details: {len(details)} fields")
            print(f"        Photos: {len(photos)}, Layouts: {len(layouts)}")

        except Exception as e:
            print(f"        Error: {e}")
            continue

    # Create output
    output = {
        'street': STREET_NAME,
        'scraped_at': datetime.now().isoformat(),
        'total_properties_found': len(property_links),
        'properties_scraped': len(properties),
        'all_property_pids': [p['pid'] for p in property_links],
        'properties': properties
    }

    return output


def main():
    result = scrape_wachusett_street()

    if result:
        # Save to JSON
        output_file = "/home/user/datacollection/wachusett_st.json"
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)

        print("\n" + "=" * 60)
        print(f"SUCCESS! Data saved to: {output_file}")
        print("=" * 60)

        print(f"\nStreet: {result['street']}")
        print(f"Total properties found: {result['total_properties_found']}")
        print(f"Properties scraped: {result['properties_scraped']}")

        return output_file
    else:
        print("\n" + "=" * 60)
        print("Scraping completed - check debug files for analysis")
        print("=" * 60)
        return None


if __name__ == "__main__":
    main()
