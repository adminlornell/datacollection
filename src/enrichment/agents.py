"""
CrewAI agents for owner research and enrichment.
"""
from crewai import Agent

from .tools import (
    OwnerClassifierTool,
    MASecretaryOfStateTool,
    OpenCorporatesTool,
    SECEdgarTool,
    DuckDuckGoSearchTool
)


def setup_openrouter(model: str):
    """
    Configure OpenRouter as the LLM provider via LiteLLM.

    Returns an LLM instance configured for OpenRouter.
    """
    import os
    from crewai import LLM

    if model.startswith("openrouter/"):
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable not set")

        # Use LiteLLM format for OpenRouter
        # Format: openrouter/<provider>/<model>
        return LLM(
            model=model,  # e.g., "openrouter/meta-llama/llama-3.3-70b-instruct:free"
            api_key=api_key,
            temperature=0.7
        )

    # For non-OpenRouter models, return the model string directly
    return model


def create_classifier_agent(llm: str = "openrouter/meta-llama/llama-3.3-70b-instruct:free") -> Agent:
    """
    Creates an agent that classifies property owners as individuals or companies.
    First step in the research pipeline.
    """
    model = setup_openrouter(llm)
    return Agent(
        role="Owner Classification Specialist",
        goal=(
            "Accurately classify property owner names as either individual persons "
            "or business entities (LLC, Corporation, Trust, Partnership, etc.). "
            "Identify key indicators that reveal the entity type."
        ),
        backstory=(
            "You are an expert at analyzing names and identifying whether they belong "
            "to individuals or business entities. You have deep knowledge of business "
            "naming conventions, legal entity suffixes (LLC, Inc, Corp, Trust), and "
            "can recognize patterns that indicate corporate ownership. You understand "
            "that property records often use abbreviated or formatted names that need "
            "careful analysis."
        ),
        tools=[OwnerClassifierTool()],
        llm=model,
        verbose=True,
        allow_delegation=False,
        max_iter=3
    )


def create_researcher_agent(llm: str = "openrouter/meta-llama/llama-3.3-70b-instruct:free") -> Agent:
    """
    Creates an agent that researches companies across multiple data sources.
    Core research agent that queries MA SOS, OpenCorporates, SEC EDGAR.
    """
    model = setup_openrouter(llm)
    return Agent(
        role="Corporate Research Specialist",
        goal=(
            "Find comprehensive information about business entities by searching "
            "multiple authoritative sources. Discover officers, registered agents, "
            "parent companies, and ownership structure. Identify if owners are "
            "themselves companies that need further research."
        ),
        backstory=(
            "You are a skilled corporate researcher with expertise in navigating "
            "business registries and public records. You know how to search the "
            "Massachusetts Secretary of State database, OpenCorporates, and SEC EDGAR "
            "to find company registration details, officers, and ownership information. "
            "You understand corporate structures and can identify when a company's "
            "officers or parent entities are themselves companies that require "
            "additional research to find the ultimate beneficial owners."
        ),
        tools=[
            MASecretaryOfStateTool(),
            OpenCorporatesTool(),
            SECEdgarTool(),
            DuckDuckGoSearchTool()
        ],
        llm=model,
        verbose=True,
        allow_delegation=False,
        max_iter=10  # Allow more iterations for thorough research
    )


def create_compiler_agent(llm: str = "openrouter/meta-llama/llama-3.3-70b-instruct:free") -> Agent:
    """
    Creates an agent that compiles research findings into ownership chains.
    Final step that synthesizes all research into structured output.
    """
    model = setup_openrouter(llm)
    return Agent(
        role="Ownership Chain Compiler",
        goal=(
            "Synthesize all research findings into a clear, accurate ownership chain. "
            "Trace ownership from the property through any intermediate entities "
            "to the ultimate beneficial owners (individuals). Organize findings "
            "with proper source attribution and confidence levels."
        ),
        backstory=(
            "You are an analyst who excels at organizing complex corporate ownership "
            "information into clear, actionable reports. You can trace ownership "
            "through multiple layers of companies to identify the real people who "
            "ultimately control a property. You are meticulous about citing sources "
            "and noting the confidence level of each finding. You understand that "
            "ownership chains can be complex with holding companies, trusts, and "
            "multiple layers of corporate entities."
        ),
        tools=[],  # Compiler doesn't need external tools, just synthesizes
        llm=model,
        verbose=True,
        allow_delegation=False,
        max_iter=5
    )


def create_all_agents(llm: str = "openrouter/meta-llama/llama-3.3-70b-instruct:free") -> dict:
    """Create all agents with the specified LLM."""
    return {
        "classifier": create_classifier_agent(llm),
        "researcher": create_researcher_agent(llm),
        "compiler": create_compiler_agent(llm)
    }
