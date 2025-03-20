import asyncio
import random
from playwright.async_api import async_playwright
import sys
import os
import datetime
import json
import platform
import tempfile

# Add the project root directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.database.database import AsyncSessionLocal, URL, setup_database
from sqlalchemy import select

# Create screenshots directory if it doesn't exist
SCREENSHOTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../screenshots'))
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# List of common user agents
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
]

# Define a list of languages for Accept-Language header
LANGUAGES = ['en-US,en;q=0.9', 'en-GB,en;q=0.8', 'fr-FR,fr;q=0.9', 'de-DE,de;q=0.8', 'es-ES,es;q=0.9']

async def create_stealth_context(context):
    """Add stealth settings to an existing browser context to avoid detection"""
    # Extra headers to appear more like a real browser
    await context.set_extra_http_headers({
        'Accept-Language': random.choice(LANGUAGES),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'DNT': '1',
    })

    # Add webGL, canvas, and audio fingerprinting scripts to make browser appear more normal
    await context.add_init_script("""
        () => {
            // Override webGL fingerprinting
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                // Add randomization to WebGL fingerprinting
                if (parameter === 37445) {
                    return 'Intel Inc.';
                }
                if (parameter === 37446) {
                    return 'Intel Iris Graphics';
                }
                return getParameter.apply(this, arguments);
            };
            
            // Override the navigator object
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });
            
            // Fake plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    return [
                        {
                            0: {type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format"},
                            description: "Chrome PDF Plugin",
                            filename: "internal-pdf-viewer",
                            name: "Chrome PDF Plugin",
                            length: 1
                        },
                        {
                            0: {type: "application/pdf", suffixes: "pdf", description: "Portable Document Format"},
                            description: "Chrome PDF Viewer",
                            filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai",
                            name: "Chrome PDF Viewer",
                            length: 1
                        }
                    ];
                }
            });
        }
    """)

async def visit_url(url: str, semaphore: asyncio.Semaphore, context):
    """Visit a URL, wait a random time, save a screenshot, and then close the page"""
    async with semaphore:
        try:
            page = await context.new_page()
            
            print(f"Visiting {url}")
            
            # Set cookies - this can help with bypassing some detections
            await context.add_cookies([
                {
                    "name": "cf_clearance",  # Common Cloudflare cookie
                    "value": f"random_{random.randint(1000000, 9999999)}",
                    "domain": url.split('/')[2] if url.startswith('http') else url.split('/')[0],
                    "path": "/",
                }
            ])
            
            # Configure additional page settings
            await page.set_viewport_size({"width": random.randint(1050, 1920), "height": random.randint(800, 1080)})
            
            # Add random delays between actions to simulate human behavior
            await asyncio.sleep(random.uniform(0.5, 2))
            
            # Visit with more natural navigation options
            await page.goto(url, timeout=60000, wait_until="domcontentloaded")
            
            # Simulate scrolling like a human would
            for _ in range(random.randint(2, 5)):
                await page.mouse.wheel(0, random.randint(100, 300))
                await asyncio.sleep(random.uniform(0.3, 1))
            
            # Move mouse randomly
            await page.mouse.move(random.randint(100, 700), random.randint(100, 500))
            
            # Wait a random time between 4-10 seconds (more realistic)
            wait_time = random.uniform(4, 10)
            print(f"Waiting {wait_time:.2f} seconds on {url}")
            await asyncio.sleep(wait_time)
            
            # Wait for network to be idle to ensure page is fully loaded
            await page.wait_for_load_state('networkidle')
            
            # Create a safe filename from the URL
            safe_filename = url.replace('://', '_').replace('/', '_').replace('?', '_').replace('&', '_')
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            screenshot_path = os.path.join(SCREENSHOTS_DIR, f"{safe_filename}_{timestamp}.png")
            
            # Save screenshot
            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"Screenshot saved to {screenshot_path}")
            
            print(f"Done with {url}")
            await page.close()  # Close just the page, keep the context open
        except Exception as e:
            print(f"Error visiting {url}: {e}")

async def main():
    # Setup database if it doesn't exist
    await setup_database()
    
    # Create a semaphore to limit concurrent page loads
    semaphore = asyncio.Semaphore(3)
    
    # Get URLs from the database
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(URL))
        urls = result.scalars().all()
    
    # Extract actual URLs from the URL objects
    url_strings = [url.url for url in urls]
    print(f"Found {len(url_strings)} URLs in the database.")
    
    # Create temp directory for user data
    user_data_dir = tempfile.mkdtemp(prefix='playwright_')
    print(f"Created user data directory at: {user_data_dir}")
    
    # Launch playwright browser with persistent context
    async with async_playwright() as p:
        # Use launch_persistent_context instead of launch
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-site-isolation-trials',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--ignore-certificate-errors',
                '--ignore-certificate-errors-spki-list',
                '--enable-features=NetworkService',
                f'--window-size={random.randint(1050, 1920)},{random.randint(800, 1080)}',
                '--hide-scrollbars',
                '--mute-audio',
                '--disable-gpu',
            ],
            ignore_default_args=['--enable-automation'],
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": random.randint(1050, 1920), "height": random.randint(800, 1080)},
            device_scale_factor=random.choice([1, 1.25, 1.5, 1.75, 2]),
            locale=random.choice(['en-US', 'en-GB', 'fr-FR', 'de-DE']),
            timezone_id=random.choice(['America/New_York', 'Europe/London', 'Europe/Paris', 'Europe/Berlin']),
            permissions=['geolocation'],
            java_script_enabled=True,
            has_touch=random.choice([True, False]),
            color_scheme=random.choice(['dark', 'light']),
            reduced_motion=random.choice(['reduce', 'no-preference']),
        )
        
        # Apply stealth settings to the context
        await create_stealth_context(context)
        
        # Process URLs with delays between requests
        tasks = []
        for url in url_strings:
            tasks.append(visit_url(url, semaphore, context))
            # Add delay between starting each task
            await asyncio.sleep(random.uniform(2, 5))
        
        # Run the tasks with gather
        await asyncio.gather(*tasks)
        await context.close()
        
        # Clean up user data directory
        try:
            import shutil
            shutil.rmtree(user_data_dir, ignore_errors=True)
            print(f"Cleaned up user data directory: {user_data_dir}")
        except Exception as e:
            print(f"Failed to clean up user data directory: {e}")

if __name__ == "__main__":
    # Set a random seed based on current time
    random.seed(datetime.datetime.now().timestamp())
    asyncio.run(main())
