"""
Tool to classify owner names as individuals or companies.
Uses pattern matching and heuristics - no API required.
"""
import re
from typing import Type, Any, ClassVar, List

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from ..models import OwnerType, ClassificationResult


class OwnerClassifierInput(BaseModel):
    """Input schema for owner classification."""
    owner_name: str = Field(..., description="The owner name to classify")


class OwnerClassifierTool(BaseTool):
    """
    Classifies property owner names as individuals or business entities.
    Uses pattern matching to identify LLCs, corporations, trusts, etc.
    """
    name: str = "Owner Classifier"
    description: str = (
        "Analyzes an owner name to determine if it's an individual person or a "
        "business entity (LLC, Corporation, Trust, etc.). Returns the entity type "
        "and confidence score. Use this as the first step in owner research."
    )
    args_schema: Type[BaseModel] = OwnerClassifierInput

    # Entity type patterns
    CORPORATION_PATTERNS: ClassVar[List[str]] = [
        r'\b(inc\.?|incorporated|corp\.?|corporation)\b',
        r'\b(co\.?|company)\b',
        r'\bltd\.?\b',
        r'\bplc\b',
    ]

    LLC_PATTERNS: ClassVar[List[str]] = [
        r'\b(llc|l\.l\.c\.?|limited liability company)\b',
        r'\b(llp|l\.l\.p\.?|limited liability partnership)\b',
        r'\bpllc\b',
    ]

    TRUST_PATTERNS: ClassVar[List[str]] = [
        r'\b(trust|tr\.?|trustee|trustees)\b',
        r'\b(living trust|family trust|revocable trust|irrevocable trust)\b',
        r'\b(estate of|est\.? of)\b',
    ]

    PARTNERSHIP_PATTERNS: ClassVar[List[str]] = [
        r'\b(partnership|partners|lp|l\.p\.)\b',
        r'\b(general partnership|limited partnership)\b',
    ]

    GOVERNMENT_PATTERNS: ClassVar[List[str]] = [
        r'\b(city of|town of|county of|state of|commonwealth)\b',
        r'\b(municipal|municipality|government|agency)\b',
        r'\b(housing authority|school district|water district)\b',
    ]

    NONPROFIT_PATTERNS: ClassVar[List[str]] = [
        r'\b(foundation|association|assoc\.?|society)\b',
        r'\b(church|synagogue|mosque|temple)\b',
        r'\b(charity|charitable|nonprofit|non-profit)\b',
    ]

    # Individual name patterns
    INDIVIDUAL_PATTERNS: ClassVar[List[str]] = [
        r'^[A-Z][a-z]+\s+[A-Z]\.?\s+[A-Z][a-z]+$',  # First M. Last
        r'^[A-Z][a-z]+\s+[A-Z][a-z]+$',  # First Last
        r'^[A-Z][a-z]+\s+[A-Z][a-z]+\s+[A-Z][a-z]+$',  # First Middle Last
        r'^[A-Z][a-z]+,\s*[A-Z][a-z]+',  # Last, First
    ]

    # Indicators that suggest it's NOT an individual
    NON_INDIVIDUAL_INDICATORS: ClassVar[List[str]] = [
        r'\b(holdings?|properties|investments?|realty|real estate)\b',
        r'\b(development|developers?|builders?|construction)\b',
        r'\b(management|mgmt|group|partners)\b',
        r'\b(enterprises?|ventures?|capital)\b',
        r'\b(services?|solutions?|systems?)\b',
        r'\d{2,}',  # Multiple numbers often indicate a business
    ]

    def _run(self, owner_name: str, **_: Any) -> str:
        """Classify the owner name and return structured result."""
        result = self._classify(owner_name)
        return result.model_dump_json()

    def _classify(self, owner_name: str) -> ClassificationResult:
        """Perform the classification."""
        name_lower = owner_name.lower().strip()
        name_upper = owner_name.upper().strip()
        indicators = []
        confidence = 0.5

        # Check for explicit entity type indicators
        for pattern in self.LLC_PATTERNS:
            if re.search(pattern, name_lower, re.IGNORECASE):
                indicators.append("LLC indicator found")
                return ClassificationResult(
                    owner_name=owner_name,
                    owner_type=OwnerType.LLC,
                    confidence=0.95,
                    entity_indicators=indicators,
                    reasoning="Contains explicit LLC designation"
                )

        for pattern in self.CORPORATION_PATTERNS:
            if re.search(pattern, name_lower, re.IGNORECASE):
                indicators.append("Corporation indicator found")
                return ClassificationResult(
                    owner_name=owner_name,
                    owner_type=OwnerType.CORPORATION,
                    confidence=0.95,
                    entity_indicators=indicators,
                    reasoning="Contains explicit corporation designation"
                )

        for pattern in self.TRUST_PATTERNS:
            if re.search(pattern, name_lower, re.IGNORECASE):
                indicators.append("Trust indicator found")
                return ClassificationResult(
                    owner_name=owner_name,
                    owner_type=OwnerType.TRUST,
                    confidence=0.90,
                    entity_indicators=indicators,
                    reasoning="Contains trust-related terminology"
                )

        for pattern in self.PARTNERSHIP_PATTERNS:
            if re.search(pattern, name_lower, re.IGNORECASE):
                indicators.append("Partnership indicator found")
                return ClassificationResult(
                    owner_name=owner_name,
                    owner_type=OwnerType.PARTNERSHIP,
                    confidence=0.90,
                    entity_indicators=indicators,
                    reasoning="Contains partnership designation"
                )

        for pattern in self.GOVERNMENT_PATTERNS:
            if re.search(pattern, name_lower, re.IGNORECASE):
                indicators.append("Government indicator found")
                return ClassificationResult(
                    owner_name=owner_name,
                    owner_type=OwnerType.GOVERNMENT,
                    confidence=0.95,
                    entity_indicators=indicators,
                    reasoning="Contains government entity terminology"
                )

        for pattern in self.NONPROFIT_PATTERNS:
            if re.search(pattern, name_lower, re.IGNORECASE):
                indicators.append("Nonprofit indicator found")
                return ClassificationResult(
                    owner_name=owner_name,
                    owner_type=OwnerType.NONPROFIT,
                    confidence=0.85,
                    entity_indicators=indicators,
                    reasoning="Contains nonprofit organization terminology"
                )

        # Check for business-like indicators
        business_score = 0
        for pattern in self.NON_INDIVIDUAL_INDICATORS:
            if re.search(pattern, name_lower, re.IGNORECASE):
                business_score += 1
                indicators.append(f"Business indicator: {pattern}")

        if business_score >= 2:
            return ClassificationResult(
                owner_name=owner_name,
                owner_type=OwnerType.CORPORATION,
                confidence=0.7,
                entity_indicators=indicators,
                reasoning="Multiple business-related terms suggest corporate entity"
            )

        # Check for individual name patterns
        for pattern in self.INDIVIDUAL_PATTERNS:
            if re.match(pattern, owner_name):
                indicators.append("Matches individual name pattern")
                return ClassificationResult(
                    owner_name=owner_name,
                    owner_type=OwnerType.INDIVIDUAL,
                    confidence=0.85,
                    entity_indicators=indicators,
                    reasoning="Name format matches typical individual name pattern"
                )

        # Heuristic: names with 2-3 words, all starting with capitals, no numbers
        words = owner_name.split()
        if (2 <= len(words) <= 3 and
            all(w[0].isupper() for w in words if w) and
            not any(c.isdigit() for c in owner_name)):
            indicators.append("Simple name structure")
            return ClassificationResult(
                owner_name=owner_name,
                owner_type=OwnerType.INDIVIDUAL,
                confidence=0.65,
                entity_indicators=indicators,
                reasoning="Name structure suggests individual (2-3 capitalized words, no numbers)"
            )

        # Default to unknown
        return ClassificationResult(
            owner_name=owner_name,
            owner_type=OwnerType.UNKNOWN,
            confidence=0.3,
            entity_indicators=indicators,
            reasoning="Unable to confidently classify - manual review recommended"
        )

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        """Async version delegates to sync."""
        return self._run(*args, **kwargs)
