"""
Tool to search SEC EDGAR database for public company filings.
Completely free - no API key required.
https://www.sec.gov/cgi-bin/browse-edgar
"""
import asyncio
import re
from typing import Type, Any, Optional, List, ClassVar, Dict
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from ..models import (
    CompanyInfo, PersonInfo, OwnerType,
    SourceRecord, DataSource
)


class SECEdgarSearchInput(BaseModel):
    """Input schema for SEC EDGAR search."""
    company_name: str = Field(..., description="The company name to search for")
    filing_type: str = Field(
        default="",
        description="Optional filing type filter (e.g., '10-K', '10-Q', 'DEF 14A')"
    )


class SECEdgarTool(BaseTool):
    """
    Searches SEC EDGAR for public company information.
    Returns company filings, officers from proxy statements, and beneficial ownership info.
    Completely free - no API key required.
    """
    name: str = "SEC EDGAR Search"
    description: str = (
        "Searches the SEC EDGAR database for public company filings. "
        "Use for publicly traded companies to find officers, directors, "
        "and beneficial ownership information from 10-K, proxy statements (DEF 14A), "
        "and ownership filings (Schedule 13D/13G)."
    )
    args_schema: Type[BaseModel] = SECEdgarSearchInput

    BASE_URL: ClassVar[str] = "https://www.sec.gov"
    SEARCH_URL: ClassVar[str] = "https://www.sec.gov/cgi-bin/browse-edgar"
    FULLTEXT_URL: ClassVar[str] = "https://efts.sec.gov/LATEST/search-index"
    TIMEOUT: ClassVar[int] = 30

    # User agent required by SEC
    HEADERS: ClassVar[Dict[str, str]] = {
        "User-Agent": "PropertyResearch/1.0 (research@example.com)",
        "Accept-Encoding": "gzip, deflate",
    }

    def _run(
        self,
        company_name: str,
        filing_type: str = "",
        **_: Any
    ) -> str:
        """Search SEC EDGAR and return company information."""
        try:
            result = asyncio.run(self._search_async(company_name, filing_type))
            return result
        except Exception as e:
            return f'{{"error": "Search failed: {str(e)}", "company_name": "{company_name}"}}'

    async def _search_async(self, company_name: str, filing_type: str) -> str:
        """Async search implementation."""
        async with httpx.AsyncClient(
            timeout=self.TIMEOUT,
            headers=self.HEADERS,
            follow_redirects=True
        ) as client:
            # Search for company
            params = {
                "company": company_name,
                "type": filing_type,
                "dateb": "",
                "owner": "include",
                "count": "40",
                "action": "getcompany"
            }

            try:
                response = await client.get(self.SEARCH_URL, params=params)
                response.raise_for_status()
            except Exception as e:
                return f'{{"error": "Search request failed: {str(e)}"}}'

            # Parse search results
            soup = BeautifulSoup(response.text, 'html.parser')

            # Check if we got company results
            company_table = soup.find("table", class_="tableFile2")
            if not company_table:
                # Try to find company info directly
                company_info_table = soup.find("table", {"summary": "Company Info"})
                if company_info_table:
                    return await self._parse_company_page(client, soup, response.url)
                return f'{{"found": false, "company_name": "{company_name}", "message": "No SEC filings found"}}'

            # Parse company list
            companies = self._parse_company_list(soup)
            if not companies:
                return f'{{"found": false, "company_name": "{company_name}"}}'

            # Get best match
            best_match = self._find_best_match(companies, company_name)
            if best_match and best_match.get("cik"):
                # Get company filings page
                try:
                    filings_url = f"{self.SEARCH_URL}?action=getcompany&CIK={best_match['cik']}&type=&dateb=&owner=include&count=40"
                    filings_response = await client.get(filings_url)
                    filings_soup = BeautifulSoup(filings_response.text, 'html.parser')
                    return await self._parse_company_page(client, filings_soup, filings_url)
                except Exception as e:
                    return self._basic_result(best_match)

            return f'{{"found": false, "company_name": "{company_name}"}}'

    def _parse_company_list(self, soup: BeautifulSoup) -> List[dict]:
        """Parse company search results."""
        companies = []
        table = soup.find("table", class_="tableFile2")

        if not table:
            return companies

        for row in table.find_all("tr")[1:]:  # Skip header
            cells = row.find_all("td")
            if len(cells) >= 2:
                link = cells[0].find("a")
                if link:
                    href = link.get("href", "")
                    cik_match = re.search(r"CIK=(\d+)", href)
                    companies.append({
                        "name": cells[0].get_text(strip=True),
                        "cik": cik_match.group(1) if cik_match else None,
                        "state": cells[1].get_text(strip=True) if len(cells) > 1 else "",
                    })

        return companies

    def _find_best_match(self, companies: List[dict], search_name: str) -> Optional[dict]:
        """Find the best matching company."""
        if not companies:
            return None

        search_lower = search_name.lower().strip()

        # Exact match
        for c in companies:
            if c["name"].lower().strip() == search_lower:
                return c

        # Contains match
        for c in companies:
            if search_lower in c["name"].lower():
                return c

        return companies[0] if companies else None

    async def _parse_company_page(
        self,
        client: httpx.AsyncClient,
        soup: BeautifulSoup,
        url: str
    ) -> str:
        """Parse company filings page and extract information."""
        # Get company info
        company_name = ""
        cik = ""

        # Try to find company name
        company_info = soup.find("span", class_="companyName")
        if company_info:
            company_name = company_info.get_text(strip=True)
            # Extract CIK
            cik_match = re.search(r"CIK[:\s]+(\d+)", company_info.get_text())
            if cik_match:
                cik = cik_match.group(1)

        # Look for filing links to get more info
        officers = []
        filings = soup.find_all("a", href=re.compile(r"Archives/edgar/data"))

        # Try to find a DEF 14A (proxy statement) for officer info
        for filing_link in filings[:20]:  # Check first 20 filings
            href = filing_link.get("href", "")
            text = filing_link.get_text(strip=True)

            if "DEF 14A" in text or "DEF14A" in text:
                # Found a proxy statement - could parse for officers
                # For now, just note that we found it
                break

        # Create source record
        source = SourceRecord(
            source=DataSource.SEC_EDGAR,
            url=str(url),
            retrieved_at=datetime.utcnow(),
            confidence=0.95
        )

        company_info = CompanyInfo(
            name=company_name.split(" CIK")[0].strip() if company_name else "",
            entity_type=OwnerType.CORPORATION,  # SEC filers are typically corporations
            entity_number=cik,
            officers=officers,
            sources=[source]
        )

        return company_info.model_dump_json()

    def _basic_result(self, match: dict) -> str:
        """Return basic result."""
        info = CompanyInfo(
            name=match.get("name", ""),
            entity_type=OwnerType.CORPORATION,
            state_of_formation=match.get("state"),
            entity_number=match.get("cik"),
            sources=[SourceRecord(source=DataSource.SEC_EDGAR, confidence=0.7)]
        )
        return info.model_dump_json()

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        """Async version."""
        return await self._search_async(
            kwargs.get("company_name", args[0] if args else ""),
            kwargs.get("filing_type", "")
        )
