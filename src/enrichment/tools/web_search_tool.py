"""
Free web search tool using DuckDuckGo.
No API key required.
"""
import asyncio
import re
from typing import Type, Any, List, ClassVar, Dict
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from ..models import SourceRecord, DataSource


class DuckDuckGoSearchInput(BaseModel):
    """Input schema for DuckDuckGo search."""
    query: str = Field(..., description="The search query")
    max_results: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of results to return (1-10)"
    )


class WebSearchResult(BaseModel):
    """A single web search result."""
    title: str
    url: str
    snippet: str


class WebSearchOutput(BaseModel):
    """Output from web search."""
    query: str
    results: List[WebSearchResult]
    source: SourceRecord


class DuckDuckGoSearchTool(BaseTool):
    """
    Performs web searches using DuckDuckGo.
    Free, no API key required. Good for finding news, articles,
    and additional context about companies and individuals.
    """
    name: str = "Web Search"
    description: str = (
        "Performs a web search using DuckDuckGo to find information about "
        "companies, individuals, or any topic. Returns titles, URLs, and snippets. "
        "Use for finding news articles, company websites, and additional context."
    )
    args_schema: Type[BaseModel] = DuckDuckGoSearchInput

    # DuckDuckGo HTML search (no API needed)
    SEARCH_URL: ClassVar[str] = "https://html.duckduckgo.com/html/"
    TIMEOUT: ClassVar[int] = 30

    HEADERS: ClassVar[Dict[str, str]] = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }

    def _run(self, query: str, max_results: int = 5, **_: Any) -> str:
        """Perform web search and return results."""
        try:
            result = asyncio.run(self._search_async(query, max_results))
            return result
        except Exception as e:
            return f'{{"error": "Search failed: {str(e)}", "query": "{query}"}}'

    async def _search_async(self, query: str, max_results: int) -> str:
        """Async search implementation."""
        async with httpx.AsyncClient(
            timeout=self.TIMEOUT,
            headers=self.HEADERS,
            follow_redirects=True
        ) as client:
            try:
                response = await client.post(
                    self.SEARCH_URL,
                    data={"q": query, "b": ""},
                )
                response.raise_for_status()
            except Exception as e:
                return f'{{"error": "Search request failed: {str(e)}"}}'

            # Parse results
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []

            # Find result divs
            for result_div in soup.find_all("div", class_="result"):
                if len(results) >= max_results:
                    break

                # Get title and URL
                title_elem = result_div.find("a", class_="result__a")
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                url = title_elem.get("href", "")

                # DuckDuckGo uses redirect URLs, extract actual URL
                if "uddg=" in url:
                    url_match = re.search(r"uddg=([^&]+)", url)
                    if url_match:
                        from urllib.parse import unquote
                        url = unquote(url_match.group(1))

                # Get snippet
                snippet_elem = result_div.find("a", class_="result__snippet")
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""

                if title and url:
                    results.append(WebSearchResult(
                        title=title,
                        url=url,
                        snippet=snippet
                    ))

            output = WebSearchOutput(
                query=query,
                results=results,
                source=SourceRecord(
                    source=DataSource.WEB_SEARCH,
                    url=self.SEARCH_URL,
                    retrieved_at=datetime.utcnow(),
                    confidence=0.6
                )
            )

            return output.model_dump_json()

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        """Async version."""
        return await self._search_async(
            kwargs.get("query", args[0] if args else ""),
            kwargs.get("max_results", 5)
        )
