"""
Tool to search Massachusetts Secretary of State Corporations database.
Free public data source: https://corp.sec.state.ma.us/CorpWeb/CorpSearch/CorpSearch.aspx
"""
import re
import asyncio
from typing import Type, Any, Optional, List, Dict, ClassVar
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from ..models import (
    CompanyInfo, PersonInfo, Address, OwnerType,
    SourceRecord, DataSource
)


class MASOSSearchInput(BaseModel):
    """Input schema for MA SOS search."""
    company_name: str = Field(..., description="The company name to search for")
    exact_match: bool = Field(
        default=False,
        description="If True, search for exact name match. If False, search contains."
    )


class MASecretaryOfStateTool(BaseTool):
    """
    Searches the Massachusetts Secretary of State Corporations database.
    Returns company registration info, officers, registered agent, and status.
    Free public data source - no API key required.
    """
    name: str = "MA Secretary of State Search"
    description: str = (
        "Searches the Massachusetts Secretary of State business registry for company "
        "information. Returns officers, registered agent, formation date, status, and "
        "entity type. Use for companies registered in Massachusetts."
    )
    args_schema: Type[BaseModel] = MASOSSearchInput

    BASE_URL: ClassVar[str] = "https://corp.sec.state.ma.us"
    SEARCH_URL: ClassVar[str] = "https://corp.sec.state.ma.us/CorpWeb/CorpSearch/CorpSearch.aspx"
    DETAIL_URL: ClassVar[str] = "https://corp.sec.state.ma.us/CorpWeb/CorpSearch/CorpSummary.aspx"

    # Timeout and retry settings
    TIMEOUT: ClassVar[int] = 30
    MAX_RETRIES: ClassVar[int] = 3

    def _run(self, company_name: str, exact_match: bool = False, **_: Any) -> str:
        """Search MA SOS and return company information."""
        try:
            result = asyncio.run(self._search_async(company_name, exact_match))
            return result
        except Exception as e:
            return f'{{"error": "Search failed: {str(e)}", "company_name": "{company_name}"}}'

    async def _search_async(self, company_name: str, exact_match: bool) -> str:
        """Async search implementation."""
        async with httpx.AsyncClient(timeout=self.TIMEOUT, follow_redirects=True) as client:
            # First, get the search page to obtain viewstate
            try:
                search_page = await client.get(self.SEARCH_URL)
                search_page.raise_for_status()
            except Exception as e:
                return f'{{"error": "Failed to load search page: {str(e)}"}}'

            soup = BeautifulSoup(search_page.text, 'html.parser')

            # Extract ASP.NET viewstate fields
            viewstate = self._get_viewstate(soup)
            if not viewstate:
                return '{"error": "Could not extract form state from search page"}'

            # Prepare search form data
            search_type = "ExactName" if exact_match else "ContainsName"
            form_data = {
                "__VIEWSTATE": viewstate.get("__VIEWSTATE", ""),
                "__VIEWSTATEGENERATOR": viewstate.get("__VIEWSTATEGENERATOR", ""),
                "__EVENTVALIDATION": viewstate.get("__EVENTVALIDATION", ""),
                "ctl00$MainContent$txtEntityName": company_name,
                "ctl00$MainContent$ddlSearchType": search_type,
                "ctl00$MainContent$btnSearch": "Search"
            }

            # Submit search
            try:
                search_result = await client.post(
                    self.SEARCH_URL,
                    data=form_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                search_result.raise_for_status()
            except Exception as e:
                return f'{{"error": "Search request failed: {str(e)}"}}'

            # Parse search results
            results = self._parse_search_results(search_result.text)

            if not results:
                return f'{{"found": false, "company_name": "{company_name}", "message": "No matching companies found"}}'

            # Get details for the best match
            best_match = self._find_best_match(results, company_name)
            if best_match and best_match.get("detail_url"):
                try:
                    detail_page = await client.get(
                        f"{self.BASE_URL}{best_match['detail_url']}"
                    )
                    company_info = self._parse_company_detail(
                        detail_page.text,
                        best_match
                    )
                    return company_info.model_dump_json()
                except Exception as e:
                    # Return basic info if detail fetch fails
                    return self._basic_result(best_match)

            return self._basic_result(best_match) if best_match else f'{{"found": false, "company_name": "{company_name}"}}'

    def _get_viewstate(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract ASP.NET viewstate fields."""
        viewstate = {}
        for field_name in ["__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"]:
            field = soup.find("input", {"name": field_name})
            if field:
                viewstate[field_name] = field.get("value", "")
        return viewstate

    def _parse_search_results(self, html: str) -> List[Dict[str, Any]]:
        """Parse search results page."""
        soup = BeautifulSoup(html, 'html.parser')
        results = []

        # Look for results table
        table = soup.find("table", {"id": "MainContent_grdSearchResults"})
        if not table:
            # Try alternate table ID
            table = soup.find("table", class_="GridView")

        if not table:
            return results

        rows = table.find_all("tr")[1:]  # Skip header row
        for row in rows:
            cells = row.find_all("td")
            if len(cells) >= 3:
                link = cells[0].find("a")
                result = {
                    "name": cells[0].get_text(strip=True),
                    "entity_type": cells[1].get_text(strip=True) if len(cells) > 1 else "",
                    "status": cells[2].get_text(strip=True) if len(cells) > 2 else "",
                    "detail_url": link.get("href") if link else None
                }
                results.append(result)

        return results

    def _find_best_match(
        self,
        results: List[Dict[str, Any]],
        search_name: str
    ) -> Optional[Dict[str, Any]]:
        """Find the best matching result."""
        if not results:
            return None

        search_lower = search_name.lower().strip()

        # First, look for exact match
        for r in results:
            if r["name"].lower().strip() == search_lower:
                return r

        # Then, look for active companies with closest name match
        active_results = [r for r in results if "active" in r.get("status", "").lower()]
        if active_results:
            return active_results[0]

        return results[0]

    def _parse_company_detail(
        self,
        html: str,
        basic_info: Dict[str, Any]
    ) -> CompanyInfo:
        """Parse company detail page."""
        soup = BeautifulSoup(html, 'html.parser')

        # Extract various fields
        def get_field(label: str) -> Optional[str]:
            """Find a field value by its label."""
            label_elem = soup.find(string=re.compile(label, re.IGNORECASE))
            if label_elem:
                parent = label_elem.parent
                if parent:
                    # Try to find adjacent value
                    next_elem = parent.find_next_sibling()
                    if next_elem:
                        return next_elem.get_text(strip=True)
                    # Try parent's next sibling
                    next_elem = parent.parent.find_next_sibling() if parent.parent else None
                    if next_elem:
                        return next_elem.get_text(strip=True)
            return None

        # Determine entity type
        entity_type_str = basic_info.get("entity_type", "")
        entity_type = self._map_entity_type(entity_type_str)

        # Parse officers
        officers = self._parse_officers(soup)
        registered_agent = self._parse_registered_agent(soup)

        # Parse addresses
        principal_address = self._parse_address(soup, "Principal Office")
        registered_address = self._parse_address(soup, "Registered Agent")

        # Create source record
        source = SourceRecord(
            source=DataSource.MA_SOS,
            url=f"{self.BASE_URL}{basic_info.get('detail_url', '')}",
            retrieved_at=datetime.utcnow(),
            confidence=0.95
        )

        return CompanyInfo(
            name=basic_info.get("name", ""),
            entity_type=entity_type,
            state_of_formation="MA",
            status=basic_info.get("status", ""),
            entity_number=get_field("ID Number") or get_field("Entity ID"),
            formation_date=get_field("Date of Organization") or get_field("Formation Date"),
            registered_address=registered_address,
            principal_address=principal_address,
            registered_agent=registered_agent,
            officers=officers,
            sources=[source]
        )

    def _map_entity_type(self, type_str: str) -> OwnerType:
        """Map MA SOS entity type to our OwnerType enum."""
        type_lower = type_str.lower()
        if "llc" in type_lower or "limited liability" in type_lower:
            return OwnerType.LLC
        elif "corp" in type_lower or "inc" in type_lower:
            return OwnerType.CORPORATION
        elif "partnership" in type_lower or "lp" in type_lower:
            return OwnerType.PARTNERSHIP
        elif "trust" in type_lower:
            return OwnerType.TRUST
        elif "nonprofit" in type_lower or "non-profit" in type_lower:
            return OwnerType.NONPROFIT
        else:
            return OwnerType.CORPORATION

    def _parse_officers(self, soup: BeautifulSoup) -> List[PersonInfo]:
        """Parse officers/managers from the page."""
        officers = []

        # Look for officers section
        officers_section = soup.find(string=re.compile(r"Officers|Directors|Managers", re.IGNORECASE))
        if officers_section:
            parent = officers_section.find_parent("div") or officers_section.find_parent("table")
            if parent:
                # Look for name patterns
                for text in parent.stripped_strings:
                    if re.match(r'^[A-Z][a-z]+\s+[A-Z]', text):
                        # Looks like a name
                        officers.append(PersonInfo(
                            name=text,
                            sources=[SourceRecord(source=DataSource.MA_SOS, confidence=0.8)]
                        ))

        return officers[:10]  # Limit to first 10

    def _parse_registered_agent(self, soup: BeautifulSoup) -> Optional[PersonInfo]:
        """Parse registered agent information."""
        agent_section = soup.find(string=re.compile(r"Registered Agent", re.IGNORECASE))
        if agent_section:
            parent = agent_section.find_parent("div") or agent_section.find_parent("tr")
            if parent:
                text = parent.get_text(separator=" ", strip=True)
                # Remove the label
                text = re.sub(r"Registered Agent:?\s*", "", text, flags=re.IGNORECASE)
                if text:
                    return PersonInfo(
                        name=text.split("\n")[0].strip(),
                        role="Registered Agent",
                        sources=[SourceRecord(source=DataSource.MA_SOS, confidence=0.9)]
                    )
        return None

    def _parse_address(self, soup: BeautifulSoup, section_name: str) -> Optional[Address]:
        """Parse an address from a section."""
        section = soup.find(string=re.compile(section_name, re.IGNORECASE))
        if section:
            parent = section.find_parent("div") or section.find_parent("tr")
            if parent:
                text = parent.get_text(separator="\n", strip=True)
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if len(lines) > 1:
                    return Address(raw=" ".join(lines[1:]))
        return None

    def _basic_result(self, match: Dict[str, Any]) -> str:
        """Return basic result when details can't be fetched."""
        info = CompanyInfo(
            name=match.get("name", ""),
            entity_type=self._map_entity_type(match.get("entity_type", "")),
            state_of_formation="MA",
            status=match.get("status", ""),
            sources=[SourceRecord(source=DataSource.MA_SOS, confidence=0.7)]
        )
        return info.model_dump_json()

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        """Async version."""
        return await self._search_async(
            kwargs.get("company_name", args[0] if args else ""),
            kwargs.get("exact_match", False)
        )
