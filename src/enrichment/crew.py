"""
CrewAI crew for owner research and enrichment.
Orchestrates agents to research property owners and build ownership chains.
"""
from typing import Optional
from crewai import Crew, Task, Process

from .agents import create_all_agents
from .models import OwnershipChain, ClassificationResult, OwnerType


def create_classification_task(
    owner_name: str,
    property_address: str,
    classifier_agent
) -> Task:
    """Create task to classify an owner name."""
    return Task(
        description=f"""
Analyze the following property owner name and determine if it belongs to an
individual person or a business entity.

Owner Name: {owner_name}
Property Address: {property_address}

Use the Owner Classifier tool to analyze the name. Look for indicators like:
- Business suffixes: LLC, Inc, Corp, Trust, LP, etc.
- Business terms: Holdings, Properties, Investments, Realty, etc.
- Name patterns that suggest individual vs company

Return a classification with confidence level and reasoning.
""",
        expected_output="""
A JSON object containing:
- owner_name: The original owner name
- owner_type: One of: individual, corporation, llc, trust, partnership, government, nonprofit, unknown
- confidence: A confidence score between 0 and 1
- entity_indicators: List of indicators found in the name
- reasoning: Explanation for the classification
""",
        agent=classifier_agent
    )


def create_research_task(
    entity_name: str,
    entity_type: str,
    researcher_agent,
    context_tasks: Optional[list] = None
) -> Task:
    """Create task to research a company."""
    return Task(
        description=f"""
Research the following business entity to find ownership information:

Entity Name: {entity_name}
Entity Type: {entity_type}

Search Strategy:
1. First, search the MA Secretary of State database for company registration,
   officers, and registered agent information.
2. Then search OpenCorporates for additional details and cross-reference.
3. If it appears to be a large/public company, check SEC EDGAR for filings.
4. Use web search to find any additional context (news, company website).

For each source, extract:
- Officers, directors, managers, or members (the people running the company)
- Registered agent information
- Parent company if mentioned
- Formation date and status
- Any other ownership indicators

IMPORTANT: If any officers/members are themselves companies (not individuals),
note them as requiring further research.
""",
        expected_output="""
A comprehensive JSON report containing:
- entity_name: The researched entity
- entity_type: Confirmed entity type
- found: Whether information was found
- company_info: Full company details including officers, registered agent, etc.
- child_entities: List of any company names found that need further research
- sources: All sources consulted with URLs and confidence levels
""",
        agent=researcher_agent,
        context=context_tasks or []
    )


def create_compilation_task(
    property_parcel_id: str,
    property_address: str,
    original_owner: str,
    compiler_agent,
    context_tasks: list
) -> Task:
    """Create task to compile ownership chain."""
    return Task(
        description=f"""
Compile all research findings into a complete ownership chain for this property:

Property Parcel ID: {property_parcel_id}
Property Address: {property_address}
Original Owner (from property records): {original_owner}

Based on the research conducted, create a structured ownership chain that traces
ownership from the property to the ultimate beneficial owners (individuals).

The chain should show:
1. The direct owner of the property
2. Any intermediate holding companies or entities
3. The officers/members of each entity
4. The ultimate beneficial owners (the actual people who control the property)

For each link in the chain, include:
- Entity or person name
- Their role/relationship (owner, manager, member, officer, etc.)
- The source of this information
- Confidence level

If the research hit a dead end or couldn't find ultimate owners, note this clearly.
If any entities need further research, list them.
""",
        expected_output="""
A structured ownership chain JSON containing:
- property_parcel_id: The parcel ID
- property_address: The address
- original_owner_name: From property records
- original_owner_type: Classification result
- chain: List of ownership links from property to ultimate owners
- ultimate_owners: List of individuals identified as beneficial owners
- research_completed: Whether research found ultimate owners
- sources_consulted: All data sources used
- errors: Any issues encountered
""",
        agent=compiler_agent,
        context=context_tasks,
        output_json=OwnershipChain
    )


class OwnerResearchCrew:
    """
    Crew that researches property owners and builds ownership chains.
    Uses multiple agents and data sources to trace ownership.
    """

    def __init__(
        self,
        llm: str = "openrouter/meta-llama/llama-3.3-70b-instruct:free",
        max_research_depth: int = 3,
        verbose: bool = True
    ):
        """
        Initialize the owner research crew.

        Args:
            llm: The LLM model to use (e.g., "gpt-4o-mini", "claude-3-sonnet")
            max_research_depth: Maximum levels of ownership to trace
            verbose: Whether to show detailed output
        """
        self.llm = llm
        self.max_research_depth = max_research_depth
        self.verbose = verbose

        # Create agents
        agents = create_all_agents(llm)
        self.classifier = agents["classifier"]
        self.researcher = agents["researcher"]
        self.compiler = agents["compiler"]

    def research_owner(
        self,
        owner_name: str,
        property_parcel_id: str,
        property_address: str
    ) -> OwnershipChain:
        """
        Research a property owner and build ownership chain.

        Args:
            owner_name: The owner name from property records
            property_parcel_id: The parcel ID
            property_address: The property address

        Returns:
            OwnershipChain with all research findings
        """
        tasks = []

        # Task 1: Classify the owner
        classification_task = create_classification_task(
            owner_name=owner_name,
            property_address=property_address,
            classifier_agent=self.classifier
        )
        tasks.append(classification_task)

        # Task 2: Research if it's a company
        research_task = create_research_task(
            entity_name=owner_name,
            entity_type="unknown",  # Will be determined by classification
            researcher_agent=self.researcher,
            context_tasks=[classification_task]
        )
        tasks.append(research_task)

        # Task 3: Compile findings
        compilation_task = create_compilation_task(
            property_parcel_id=property_parcel_id,
            property_address=property_address,
            original_owner=owner_name,
            compiler_agent=self.compiler,
            context_tasks=[classification_task, research_task]
        )
        tasks.append(compilation_task)

        # Create and run the crew
        crew = Crew(
            agents=[self.classifier, self.researcher, self.compiler],
            tasks=tasks,
            process=Process.sequential,
            verbose=self.verbose
        )

        result = crew.kickoff()

        # Parse CrewAI result - try multiple approaches
        try:
            # Approach 1: Pydantic output (if output_pydantic was used)
            if hasattr(result, 'pydantic') and result.pydantic:
                return result.pydantic

            # Approach 2: JSON dict output (from output_json)
            if hasattr(result, 'json_dict') and result.json_dict:
                return OwnershipChain(**result.json_dict)

            # Approach 3: Direct dict
            if isinstance(result, dict):
                return OwnershipChain(**result)

            # Approach 4: Parse raw string output
            if hasattr(result, 'raw') and result.raw:
                import json
                import re
                raw = result.raw

                # Try to find JSON in the raw output
                json_match = re.search(r'\{[\s\S]*\}', raw)
                if json_match:
                    try:
                        parsed = json.loads(json_match.group())
                        # Ensure required fields
                        parsed.setdefault('property_parcel_id', property_parcel_id)
                        parsed.setdefault('property_address', property_address)
                        parsed.setdefault('original_owner_name', owner_name)
                        return OwnershipChain(**parsed)
                    except json.JSONDecodeError:
                        pass

            # Approach 5: Try to construct from tasks_output
            if hasattr(result, 'tasks_output') and result.tasks_output:
                last_task = result.tasks_output[-1]
                if hasattr(last_task, 'pydantic') and last_task.pydantic:
                    return last_task.pydantic
                if hasattr(last_task, 'json_dict') and last_task.json_dict:
                    return OwnershipChain(**last_task.json_dict)
                if hasattr(last_task, 'raw') and last_task.raw:
                    import json
                    import re
                    raw = last_task.raw
                    json_match = re.search(r'\{[\s\S]*\}', raw)
                    if json_match:
                        try:
                            parsed = json.loads(json_match.group())
                            parsed.setdefault('property_parcel_id', property_parcel_id)
                            parsed.setdefault('property_address', property_address)
                            parsed.setdefault('original_owner_name', owner_name)
                            return OwnershipChain(**parsed)
                        except json.JSONDecodeError:
                            pass

            # Fallback: Create minimal result with error
            return OwnershipChain(
                property_parcel_id=property_parcel_id,
                property_address=property_address,
                original_owner_name=owner_name,
                original_owner_type=OwnerType.UNKNOWN,
                research_completed=False,
                errors=[f"Could not parse result: {str(result)[:500]}"]
            )
        except Exception as e:
            return OwnershipChain(
                property_parcel_id=property_parcel_id,
                property_address=property_address,
                original_owner_name=owner_name,
                original_owner_type=OwnerType.UNKNOWN,
                research_completed=False,
                errors=[f"Error parsing result: {str(e)}"]
            )

    def research_owner_deep(
        self,
        owner_name: str,
        property_parcel_id: str,
        property_address: str
    ) -> OwnershipChain:
        """
        Perform deep research with multiple iterations to find ultimate owners.
        Follows ownership chains through multiple levels of companies.

        Args:
            owner_name: The owner name from property records
            property_parcel_id: The parcel ID
            property_address: The property address

        Returns:
            OwnershipChain with complete ownership trace
        """
        # Start with initial research
        result = self.research_owner(owner_name, property_parcel_id, property_address)

        # Track entities we've already researched to avoid loops
        researched_entities = {owner_name.lower()}

        # Iteratively research child entities
        depth = 1
        entities_to_research = []

        # Extract any child entities from the initial result
        for link in result.chain:
            if link.company_info:
                for officer in link.company_info.officers:
                    if (officer.name.lower() not in researched_entities and
                        self._looks_like_company(officer.name)):
                        entities_to_research.append(officer.name)

                if link.company_info.parent_company:
                    parent = link.company_info.parent_company
                    if parent.lower() not in researched_entities:
                        entities_to_research.append(parent)

        # Research additional entities up to max depth
        while entities_to_research and depth < self.max_research_depth:
            entity = entities_to_research.pop(0)
            if entity.lower() in researched_entities:
                continue

            researched_entities.add(entity.lower())
            depth += 1

            # Research this entity
            sub_result = self.research_owner(entity, property_parcel_id, property_address)

            # Add findings to main result
            result.chain.extend(sub_result.chain)
            result.sources_consulted.extend(sub_result.sources_consulted)

            # Check for more entities to research
            for link in sub_result.chain:
                if link.company_info:
                    for officer in link.company_info.officers:
                        if (officer.name.lower() not in researched_entities and
                            self._looks_like_company(officer.name)):
                            entities_to_research.append(officer.name)

        if depth >= self.max_research_depth and entities_to_research:
            result.max_depth_reached = True
            result.errors.append(
                f"Max research depth ({self.max_research_depth}) reached. "
                f"Remaining entities: {entities_to_research[:5]}"
            )

        result.research_completed = True
        return result

    def _looks_like_company(self, name: str) -> bool:
        """Check if a name looks like a company rather than an individual."""
        company_indicators = [
            'llc', 'inc', 'corp', 'ltd', 'company', 'co.',
            'holdings', 'properties', 'investments', 'trust',
            'partnership', 'lp', 'llp', 'group', 'enterprises'
        ]
        name_lower = name.lower()
        return any(indicator in name_lower for indicator in company_indicators)
