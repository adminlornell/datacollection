"""
Tool to search OpenCorporates database.
Free API tier available: https://api.opencorporates.com/
"""
import asyncio
from typing import Type, Any, Optional, List, ClassVar
from datetime import datetime

import httpx
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from ..models import (
    CompanyInfo, PersonInfo, Address, OwnerType,
    SourceRecord, DataSource
)


class OpenCorporatesSearchInput(BaseModel):
    """Input schema for OpenCorporates search."""
    company_name: str = Field(..., description="The company name to search for")
    jurisdiction: str = Field(
        default="us_ma",
        description="Jurisdiction code (e.g., 'us_ma' for Massachusetts, 'us' for all US)"
    )


class OpenCorporatesTool(BaseTool):
    """
    Searches the OpenCorporates global company database.
    Free tier allows basic company searches without API key.
    Returns company info, officers, and registration details.
    """
    name: str = "OpenCorporates Search"
    description: str = (
        "Searches OpenCorporates, a global database of company information. "
        "Use jurisdiction 'us_ma' for Massachusetts companies, 'us' for all US, "
        "or leave empty for global search. Returns officers, status, and registration details."
    )
    args_schema: Type[BaseModel] = OpenCorporatesSearchInput

    BASE_URL: ClassVar[str] = "https://api.opencorporates.com/v0.4"
    TIMEOUT: ClassVar[int] = 30

    def _run(
        self,
        company_name: str,
        jurisdiction: str = "us_ma",
        **_: Any
    ) -> str:
        """Search OpenCorporates and return company information."""
        try:
            result = asyncio.run(self._search_async(company_name, jurisdiction))
            return result
        except Exception as e:
            return f'{{"error": "Search failed: {str(e)}", "company_name": "{company_name}"}}'

    async def _search_async(self, company_name: str, jurisdiction: str) -> str:
        """Async search implementation."""
        async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
            # Search for companies
            params = {
                "q": company_name,
                "order": "score"
            }

            if jurisdiction:
                params["jurisdiction_code"] = jurisdiction

            try:
                response = await client.get(
                    f"{self.BASE_URL}/companies/search",
                    params=params
                )

                # Handle rate limiting
                if response.status_code == 429:
                    return '{"error": "Rate limited by OpenCorporates. Please try again later."}'

                if response.status_code != 200:
                    return f'{{"error": "API returned status {response.status_code}"}}'

                data = response.json()

            except Exception as e:
                return f'{{"error": "Request failed: {str(e)}"}}'

            results = data.get("results", {}).get("companies", [])

            if not results:
                return f'{{"found": false, "company_name": "{company_name}", "message": "No matching companies found"}}'

            # Get the best match
            best_match = self._find_best_match(results, company_name)

            if best_match:
                # Try to get detailed info
                company_url = best_match.get("company", {}).get("opencorporates_url", "")
                if company_url:
                    try:
                        api_url = company_url.replace(
                            "https://opencorporates.com",
                            self.BASE_URL
                        )
                        detail_response = await client.get(api_url)
                        if detail_response.status_code == 200:
                            detail_data = detail_response.json()
                            company_info = self._parse_company_detail(
                                detail_data.get("results", {}).get("company", {})
                            )
                            return company_info.model_dump_json()
                    except Exception:
                        pass

                # Fall back to search result data
                company_info = self._parse_company_detail(best_match.get("company", {}))
                return company_info.model_dump_json()

            return f'{{"found": false, "company_name": "{company_name}"}}'

    def _find_best_match(
        self,
        results: List[dict],
        search_name: str
    ) -> Optional[dict]:
        """Find the best matching company."""
        if not results:
            return None

        search_lower = search_name.lower().strip()

        # First, look for exact match
        for r in results:
            company = r.get("company", {})
            if company.get("name", "").lower().strip() == search_lower:
                return r

        # Then, look for active companies
        active_results = [
            r for r in results
            if r.get("company", {}).get("current_status", "").lower() in
               ["active", "good standing", "in good standing"]
        ]

        if active_results:
            return active_results[0]

        return results[0]

    def _parse_company_detail(self, company: dict) -> CompanyInfo:
        """Parse company data from OpenCorporates API response."""
        # Determine entity type
        company_type = company.get("company_type", "")
        entity_type = self._map_entity_type(company_type)

        # Parse address
        registered_address = None
        addr = company.get("registered_address", {})
        if addr:
            registered_address = Address(
                street=addr.get("street_address"),
                city=addr.get("locality"),
                state=addr.get("region"),
                zip_code=addr.get("postal_code"),
                country=addr.get("country", "USA"),
                raw=company.get("registered_address_in_full")
            )

        # Parse officers
        officers = []
        for officer_data in company.get("officers", [])[:10]:
            officer = officer_data.get("officer", {})
            officers.append(PersonInfo(
                name=officer.get("name", ""),
                role=officer.get("position", ""),
                sources=[SourceRecord(
                    source=DataSource.OPENCORPORATES,
                    confidence=0.85
                )]
            ))

        # Parse registered agent
        registered_agent = None
        agent_name = company.get("agent_name")
        if agent_name:
            registered_agent = PersonInfo(
                name=agent_name,
                role="Registered Agent",
                address=Address(raw=company.get("agent_address")) if company.get("agent_address") else None,
                sources=[SourceRecord(source=DataSource.OPENCORPORATES, confidence=0.85)]
            )

        # Create source record
        source = SourceRecord(
            source=DataSource.OPENCORPORATES,
            url=company.get("opencorporates_url", ""),
            retrieved_at=datetime.utcnow(),
            confidence=0.9,
            raw_data=company
        )

        # Map jurisdiction to state
        jurisdiction = company.get("jurisdiction_code", "")
        state = jurisdiction.replace("us_", "").upper() if jurisdiction.startswith("us_") else None

        return CompanyInfo(
            name=company.get("name", ""),
            entity_type=entity_type,
            state_of_formation=state,
            formation_date=company.get("incorporation_date"),
            status=company.get("current_status", ""),
            entity_number=company.get("company_number"),
            registered_address=registered_address,
            registered_agent=registered_agent,
            officers=officers,
            sources=[source]
        )

    def _map_entity_type(self, type_str: str) -> OwnerType:
        """Map OpenCorporates company type to our OwnerType enum."""
        type_lower = type_str.lower()
        if "llc" in type_lower or "limited liability company" in type_lower:
            return OwnerType.LLC
        elif "corporation" in type_lower or "inc" in type_lower:
            return OwnerType.CORPORATION
        elif "partnership" in type_lower:
            return OwnerType.PARTNERSHIP
        elif "trust" in type_lower:
            return OwnerType.TRUST
        elif "nonprofit" in type_lower or "non-profit" in type_lower:
            return OwnerType.NONPROFIT
        else:
            return OwnerType.CORPORATION

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        """Async version."""
        return await self._search_async(
            kwargs.get("company_name", args[0] if args else ""),
            kwargs.get("jurisdiction", "us_ma")
        )
