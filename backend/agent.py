import requests
from bs4 import BeautifulSoup
import re
from typing import List, Dict, Optional


def resolve_relative_url(href: str, base: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return base.rstrip("/") + href
    return base.rstrip("/") + "/" + href

try:
    from .data import PRODUCTS
except ImportError:
    # For standalone testing
    PRODUCTS = [
        {"name": "Gaming Laptop", "price": 1200, "rating": 4.5},
        {"name": "Business Laptop", "price": 800, "rating": 4.2},
        {"name": "Budget Laptop", "price": 400, "rating": 3.8},
    ]

def search_amazon_products(query: str, min_price: float = 0, max_price: float = float('inf'), limit: int = 10) -> List[Dict]:
    """
    Search Amazon for products with web scraping
    Note: In production, use Amazon Product Advertising API for compliance
    """
    try:
        # Format search URL
        search_term = query.replace(' ', '+')
        url = f"https://www.amazon.com/s?k={search_term}&ref=sr_pg_1"
        
        # Add price filters if specified
        if min_price > 0 or max_price < float('inf'):
            url += f"&low-price={int(min_price)}&high-price={int(max_price)}"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cookie': 'i18n-prefs=USD; lc-main=en_US; sp-cdn="L5Z9:US"'
        }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        products = []
        # Find product containers
        product_containers = soup.find_all('div', {'data-component-type': 's-search-result'})

        for container in product_containers[:limit]:
            try:
                # Extract product title
                title = ""
                # Try to find the title from the product link
                link = container.find('a', class_='a-link-normal')
                if link:
                    title_span = link.find('span')
                    if title_span:
                        title = title_span.get_text(strip=True)
                
                if not title or len(title) < 10:
                    # Fallback to previous method
                    all_spans = container.find_all('span')
                    for span in all_spans:
                        text = span.get_text(strip=True)
                        if len(text) > 10 and len(text) < 200 and not '$' in text and not 'Sponsored' in text and not 'ad based' in text:
                            title = text
                            break
                
                if not title:
                    all_h2 = container.find_all('h2')
                    for h2 in all_h2:
                        text = h2.get_text(strip=True)
                        if len(text) > 5:
                            title = text
                            break
                
                if not title:
                    continue

                # Filter out sponsored ads and promotional content
                ad_indicators = [
                    'sponsored', 'ad based', 'you\'re seeing this ad', 
                    'product\'s relevance', 'search query', 'promoted',
                    'featured brand', 'brand spotlight'
                ]
                normalized_title = title.lower().replace('’', "'").replace('‘', "'").replace('�', "'")
                if any(indicator in normalized_title for indicator in ad_indicators):
                    continue

                # Check for sponsored label in container
                sponsored_label = container.find('span', string=re.compile(r'Sponsored', re.I))
                if sponsored_label:
                    continue

                # Check for sponsored attributes or classes
                if 'sponsored' in str(container.get('class', [])).lower():
                    continue
                if container.get('data-sponsored') or container.get('data-ad'):
                    continue

                # Filter out sponsored products by URL patterns
                product_url = ""
                link_elem = container.find('a', class_='a-link-normal')
                if link_elem and 'href' in link_elem.attrs:
                    product_url = str(link_elem['href'])

                if 'sspa' in product_url or 'sp_csd' in product_url:
                    continue

                # Extract price
                price = 0.0
                price_elem = container.find('span', class_='a-price')
                if price_elem:
                    offscreen = price_elem.find('span', class_='a-offscreen')
                    if offscreen:
                        price_text = offscreen.get_text().replace('$', '').replace(',', '').strip()
                        try:
                            price = float(price_text)
                        except ValueError:
                            pass
                
                if price == 0.0:
                    # Fallback to old method
                    price_elem = container.find('span', class_='a-price-whole')
                    if price_elem:
                        price_text = price_elem.get_text().replace(',', '').replace('$', '').strip()
                        try:
                            price = float(price_text)
                        except ValueError:
                            continue
                    else:
                        continue

                # Filter by price range (additional check)
                if not (min_price <= price <= max_price):
                    continue

                # Extract rating
                rating_elem = container.find('span', class_='a-icon-alt')
                rating = 0.0
                if rating_elem:
                    rating_match = re.search(r'(\d+\.\d+)', rating_elem.get_text())
                    if rating_match:
                        rating = float(rating_match.group(1))

                # Extract product URL
                link_elem = container.find('a', class_='a-link-normal')
                product_url = ""
                if link_elem and 'href' in link_elem.attrs:
                    product_url = resolve_relative_url(link_elem['href'], "https://www.amazon.com")
                if not product_url:
                    fallback_link = container.find('a', href=True)
                    if fallback_link and 'href' in fallback_link.attrs:
                        product_url = resolve_relative_url(fallback_link['href'], "https://www.amazon.com")

                product = {
                    "name": title[:100],  # Truncate long titles
                    "price": price,
                    "rating": rating,
                    "url": product_url,
                    "source": "amazon",
                    "currency": "USD"
                }

                products.append(product)

            except Exception as e:
                continue  # Skip problematic products

        return products

    except Exception as e:
        print(f"Amazon search error: {e}")
        return []


def search_google_shopping(query: str, min_price: float = 0, max_price: float = float('inf'), limit: int = 10) -> List[Dict]:
    """
    Search Google Shopping for products across multiple retailers
    """
    try:
        # Google Shopping search URL
        search_term = query.replace(' ', '+')
        url = f"https://www.google.com/search?q={search_term}&tbm=shop"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        products = []
        # Find shopping result containers
        shopping_results = soup.find_all('div', {'class': 'sh-dgr__content'})

        for result in shopping_results[:limit]:
            try:
                # Extract product title
                title_elem = result.find('h3', class_='tAxDx')
                if not title_elem:
                    title_elem = result.find('a', class_='Lq5OHe')
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)

                # Extract price
                price_elem = result.find('span', class_='a8Pemb')
                if not price_elem:
                    price_elem = result.find('span', class_='T14wmb')

                if price_elem:
                    price_text = price_elem.get_text().replace('$', '').replace(',', '')
                    try:
                        price = float(price_text)
                    except ValueError:
                        continue
                else:
                    continue

                # Filter by price range
                if not (min_price <= price <= max_price):
                    continue

                # Extract store/merchant
                store_elem = result.find('div', class_='aULzUe')
                store = "Unknown"
                if store_elem:
                    store = store_elem.get_text(strip=True)

                # Extract rating if available
                rating = 0.0
                rating_elem = result.find('span', class_='Rsc7Yb')
                if rating_elem:
                    rating_match = re.search(r'(\d+\.\d+)', rating_elem.get_text())
                    if rating_match:
                        rating = float(rating_match.group(1))

                # Extract product link
                link_elem = result.find('a', class_='Lq5OHe')
                product_url = ""
                if link_elem and 'href' in link_elem.attrs:
                    product_url = resolve_relative_url(link_elem['href'], "https://www.google.com")
                if not product_url:
                    fallback_link = result.find('a', href=True)
                    if fallback_link and 'href' in fallback_link.attrs:
                        product_url = resolve_relative_url(fallback_link['href'], "https://www.google.com")

                product = {
                    "name": title[:100],
                    "price": price,
                    "rating": rating,
                    "store": store,
                    "url": product_url,
                    "source": "google_shopping",
                    "currency": "USD"
                }

                products.append(product)

            except Exception as e:
                continue  # Skip problematic products

        return products

    except Exception as e:
        print(f"Google Shopping search error: {e}")
        return []


def search_walmart_products(query: str, min_price: float = 0, max_price: float = float('inf'), limit: int = 10) -> List[Dict]:
    """
    Search Walmart for products
    """
    try:
        search_term = query.replace(' ', '%20')
        url = f"https://www.walmart.com/search?q={search_term}"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        products = []
        # Find product containers
        product_containers = soup.find_all('div', {'data-item-id': True})

        for container in product_containers[:limit]:
            try:
                # Extract product title
                title_elem = container.find('span', class_='w_V_DM')
                if not title_elem:
                    title_elem = container.find('a', class_='absolute')
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)

                # Extract price
                price_elem = container.find('div', class_='mr1')
                if price_elem:
                    price_text = price_elem.get_text().replace('$', '').replace(',', '')
                    try:
                        price = float(price_text)
                    except ValueError:
                        continue
                else:
                    continue

                # Filter by price range
                if not (min_price <= price <= max_price):
                    continue

                # Extract product URL
                link_elem = container.find('a', class_='absolute')
                product_url = ""
                if link_elem and 'href' in link_elem.attrs:
                    product_url = resolve_relative_url(link_elem['href'], "https://www.walmart.com")
                if not product_url:
                    fallback_link = container.find('a', href=True)
                    if fallback_link and 'href' in fallback_link.attrs:
                        product_url = resolve_relative_url(fallback_link['href'], "https://www.walmart.com")

                product = {
                    "name": title[:100],
                    "price": price,
                    "rating": 0.0,  # Walmart doesn't show ratings on search page
                    "store": "Walmart",
                    "url": product_url,
                    "source": "walmart",
                    "currency": "USD"
                }

                products.append(product)

            except Exception as e:
                continue

        return products

    except Exception as e:
        print(f"Walmart search error: {e}")
        return []


def search_bestbuy_products(query: str, min_price: float = 0, max_price: float = float('inf'), limit: int = 10) -> List[Dict]:
    """
    Search Best Buy for products
    """
    try:
        search_term = query.replace(' ', '%20')
        url = f"https://www.bestbuy.com/site/searchpage.jsp?st={search_term}"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        products = []
        # Find product containers
        product_containers = soup.find_all('li', class_='sku-item')

        for container in product_containers[:limit]:
            try:
                # Extract product title
                title_elem = container.find('h4', class_='sku-title')
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)

                # Extract price
                price_elem = container.find('div', class_='priceView-hero-price')
                if not price_elem:
                    continue

                price_text = price_elem.get_text().replace('$', '').replace(',', '')
                try:
                    price = float(price_text)
                except ValueError:
                    continue

                # Filter by price range
                if not (min_price <= price <= max_price):
                    continue

                # Extract rating
                rating = 0.0
                rating_elem = container.find('span', class_='c-review-average')
                if rating_elem:
                    try:
                        rating = float(rating_elem.get_text(strip=True))
                    except ValueError:
                        pass

                # Extract product URL
                link_elem = title_elem.find('a')
                product_url = ""
                if link_elem and 'href' in link_elem.attrs:
                    product_url = resolve_relative_url(link_elem['href'], "https://www.bestbuy.com")
                if not product_url:
                    fallback_link = container.find('a', href=True)
                    if fallback_link and 'href' in fallback_link.attrs:
                        product_url = resolve_relative_url(fallback_link['href'], "https://www.bestbuy.com")

                product = {
                    "name": title[:100],
                    "price": price,
                    "rating": rating,
                    "store": "Best Buy",
                    "url": product_url,
                    "source": "bestbuy",
                    "currency": "USD"
                }

                products.append(product)

            except Exception as e:
                continue

        return products

    except Exception as e:
        print(f"Best Buy search error: {e}")
        return []


def search_all_platforms(query: str, min_price: float = 0, max_price: float = float('inf'), limit_per_platform: int = 5) -> List[Dict]:
    """
    Search across multiple platforms and aggregate results
    """
    all_products = []

    print(f"🔍 Searching across platforms for: '{query}' (${min_price}-${max_price})")

    # Search Google Shopping (aggregates multiple retailers)
    print("  • Google Shopping...")
    google_products = search_google_shopping(query, min_price, max_price, limit_per_platform)
    all_products.extend(google_products)
    print(f"    Found {len(google_products)} products")

    # Search individual platforms
    platforms = [
        ("Amazon", search_amazon_products),
        ("Walmart", search_walmart_products),
        ("Best Buy", search_bestbuy_products),
    ]

    for platform_name, search_func in platforms:
        print(f"  • {platform_name}...")
        try:
            products = search_func(query, min_price, max_price, limit_per_platform)
            all_products.extend(products)
            print(f"    Found {len(products)} products")
        except Exception as e:
            print(f"    Error: {e}")

    # Remove duplicates (same product from different sources)
    unique_products = []
    seen_names = set()

    for product in all_products:
        name_key = product['name'].lower()[:50]  # First 50 chars as key
        if name_key not in seen_names:
            unique_products.append(product)
            seen_names.add(name_key)

    # Sort by price (lowest first)
    unique_products.sort(key=lambda x: x['price'])

    return unique_products[:limit_per_platform * 2]  # Return top results


def parse_price_range(query: str, budget: float):
    """Parse min/max from query in flexible formats."""
    min_price = 0.0
    max_price = budget

    # explicit ($500 to $600 or $500-$600)
    price_match = re.search(r'\$(\d+)(?:\s*to\s*\$|\s*-\s*\$)(\d+)', query)
    if price_match:
        min_price = float(price_match.group(1))
        max_price = float(price_match.group(2))
        query = re.sub(r'\$\d+(?:\s*to\s*\$|\s*-\s*\$)\d+', '', query).strip()
        return max(min_price, 0), min(max_price, budget), query

    # plain numeric range (500 to 600 or 500-600)
    numeric_match = re.search(r'(\d+)(?:\s*to\s*|\s*-\s*)(\d+)', query)
    if numeric_match:
        min_price = float(numeric_match.group(1))
        max_price = float(numeric_match.group(2))
        query = re.sub(r'\d+(?:\s*to\s*|\s*-\s*)\d+', '', query).strip()
        return max(min_price, 0), min(max_price, budget), query

    # under/N budget. e.g. 'under 1200' or 'below $1200'
    under_match = re.search(r'(?:under|below)\s*\$?(\d+)', query)
    if under_match:
        max_price = min(float(under_match.group(1)), budget)
        query = re.sub(r'(?:under|below)\s*\$?\d+', '', query).strip()

    return min_price, max_price, query


def decide_purchase(request):
    """
    Enhanced agent that can search both local catalog and multiple online platforms
    """
    budget = float(request.get("budget", 0))
    query = request.get("query", "").lower().strip()
    search_online = request.get("search_online", False)

    if not query or budget <= 0:
        return {"status": "error", "message": "Query and positive budget are required"}

    # First check local catalog only when an online search is not requested.
    # When search_online is true, we prefer actual web product links and only
    # fall back to local catalog if no online results are available.
    local_matches = [
        p for p in PRODUCTS
        if query in p["name"].lower() and p["price"] <= budget
    ]

    if local_matches and not search_online:
        best_local = sorted(local_matches, key=lambda x: x["price"])[0]
        return {
            "status": "approved",
            "product": best_local,
            "source": "local_catalog",
            "search_mode": "local"
        }

    if not search_online:
        return {"status": "no_match", "message": "No local match, set search_online true for web search"}

    # Parse range and form search query text
    min_price, max_price, clean_query = parse_price_range(query, budget)
    max_price = min(max_price, budget)

    debug_info = {
        "parsed_query": clean_query,
        "min_price": min_price,
        "max_price": max_price,
        "budget": budget,
        "attempts": []
    }

    # Try strict range first
    results = search_all_platforms(clean_query, min_price, max_price, limit_per_platform=5)
    # Enforce range, budget, and require a direct product URL for the paid link flow
    results = [p for p in results if p.get("price") is not None and p.get("url") and min_price <= p["price"] <= max_price and p["price"] <= budget]
    debug_info["attempts"].append({"range": f"{min_price}-{max_price}", "count": len(results)})

    if results:
        best_product = min(results, key=lambda x: x["price"])
        return {
            "status": "approved",
            "product": best_product,
            "source": "multi_platform_search",
            "search_results": results[:5],
            "search_debug": debug_info
        }

    # Fallback to all under budget (strict-over-range guard)
    if min_price > 0 or max_price < budget:
        fallback_results = search_all_platforms(clean_query, 0, budget, limit_per_platform=5)
        fallback_results = [p for p in fallback_results if p.get("price") is not None and p.get("url") and p["price"] <= budget]
        # If explicit range was set, keep only items within that range as much as possible
        if min_price > 0 or max_price < budget:
            fallback_results = [p for p in fallback_results if min_price <= p["price"] <= max_price]

        debug_info["attempts"].append({"range": f"0-{budget}", "count": len(fallback_results)})

        if fallback_results:
            best_product = min(fallback_results, key=lambda x: x["price"])
            return {
                "status": "partial",
                "message": "No strict match in requested range; showing closest under budget.",
                "product": best_product,
                "source": "multi_platform_search_fallback",
                "search_results": fallback_results[:5],
                "search_debug": debug_info
            }

    return {
        "status": "no_match",
        "message": "No products found for query within budget",
        "search_debug": debug_info
    }