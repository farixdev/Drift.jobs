import time
from urllib.parse import quote_plus

from core.scraper.base import BaseScraper, RawJob

try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
except ImportError:
    uc = None
    By = None


class LinkedInScraper(BaseScraper):
    label = "LinkedIn"
    needs_browser = True

    def search(self, keywords: list[str], location: str) -> list[RawJob]:
        if uc is None:
            return []

        query = quote_plus(" ".join(keywords[:2]))
        loc = quote_plus(location or "Remote")
        url = f"https://www.linkedin.com/jobs/search/?keywords={query}&location={loc}"

        options = uc.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")

        driver = uc.Chrome(options=options)
        jobs: list[RawJob] = []
        try:
            driver.get(url)
            time.sleep(3)
            cards = driver.find_elements(By.CLASS_NAME, "job-search-card")
            if not cards:
                cards = driver.find_elements(By.CSS_SELECTOR, "div.base-card")

            for card in cards[:45]:
                try:
                    title_el = card.find_element(
                        By.CSS_SELECTOR,
                        ".job-search-card__title, .base-search-card__title",
                    )
                    company_el = card.find_element(
                        By.CSS_SELECTOR,
                        ".job-search-card__subtitle, .base-search-card__subtitle",
                    )
                    loc_el = card.find_element(
                        By.CSS_SELECTOR,
                        ".job-search-card__location, .job-search-card__metadata-item",
                    )
                    link_el = card.find_element(By.TAG_NAME, "a")
                    jobs.append(
                        RawJob(
                            title=title_el.text.strip(),
                            company=company_el.text.strip(),
                            location=loc_el.text.strip(),
                            description=title_el.text.strip(),
                            url=link_el.get_attribute("href") or "",
                            source="linkedin",
                            job_type="",
                        )
                    )
                except Exception:
                    continue
        finally:
            driver.quit()
        return jobs
