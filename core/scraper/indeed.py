import time
from urllib.parse import quote_plus

from core.scraper.base import BaseScraper, RawJob

try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
except ImportError:
    uc = None
    By = None


class IndeedScraper(BaseScraper):
    label = "Indeed"
    needs_browser = True

    def search(self, keywords: list[str], location: str) -> list[RawJob]:
        if uc is None:
            return []

        query = quote_plus(" ".join(keywords[:2]))
        loc = quote_plus(location or "")
        url = f"https://www.indeed.com/jobs?q={query}&l={loc}"

        options = uc.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")

        driver = uc.Chrome(options=options)
        jobs: list[RawJob] = []
        try:
            driver.get(url)
            time.sleep(3)
            cards = driver.find_elements(By.CSS_SELECTOR, "div.job_seen_beacon, div.cardOutline")
            for card in cards[:45]:
                try:
                    title_el = card.find_element(By.CSS_SELECTOR, "h2.jobTitle span, a.jcs-JobTitle")
                    company_el = card.find_element(
                        By.CSS_SELECTOR, "[data-testid='company-name'], span.companyName"
                    )
                    loc_el = card.find_element(
                        By.CSS_SELECTOR, "[data-testid='text-location'], div.companyLocation"
                    )
                    link_el = card.find_element(By.CSS_SELECTOR, "h2.jobTitle a, a.jcs-JobTitle")
                    href = link_el.get_attribute("href") or ""
                    if href.startswith("/"):
                        href = f"https://www.indeed.com{href}"
                    jobs.append(
                        RawJob(
                            title=title_el.text.strip(),
                            company=company_el.text.strip(),
                            location=loc_el.text.strip(),
                            description=title_el.text.strip(),
                            url=href,
                            source="indeed",
                            job_type="",
                        )
                    )
                except Exception:
                    continue
        finally:
            driver.quit()
        return jobs
