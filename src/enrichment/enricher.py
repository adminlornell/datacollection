"""
Main enrichment orchestrator.
Integrates with the property database to enrich owner information.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Generator

from sqlalchemy.orm import Session

from ..models import Property, init_database
from .models import OwnershipChain, OwnerType
from .crew import OwnerResearchCrew

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OwnerEnricher:
    """
    Enriches property owner information using AI agents.
    Researches owners across multiple data sources to build ownership chains.
    """

    def __init__(
        self,
        db_path: str = "worcester_properties.db",
        llm: str = "openrouter/meta-llama/llama-3.3-70b-instruct:free",
        max_depth: int = 3,
        output_dir: str = "data/enrichment",
        verbose: bool = True
    ):
        """
        Initialize the enricher.

        Args:
            db_path: Path to the SQLite database
            llm: LLM model to use for agents
            max_depth: Maximum ownership chain depth to research
            output_dir: Directory to save enrichment results
            verbose: Whether to show detailed output
        """
        self.db_path = db_path
        self.llm = llm
        self.max_depth = max_depth
        self.output_dir = Path(output_dir)
        self.verbose = verbose

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self.engine, self.Session = init_database(db_path)

        # Initialize crew
        self.crew = OwnerResearchCrew(
            llm=llm,
            max_research_depth=max_depth,
            verbose=verbose
        )

        logger.info(f"OwnerEnricher initialized with LLM: {llm}, max_depth: {max_depth}")

    def get_properties_to_enrich(
        self,
        limit: Optional[int] = None,
        company_only: bool = True
    ) -> Generator[Property, None, None]:
        """
        Get properties that need owner enrichment.

        Args:
            limit: Maximum number of properties to return
            company_only: If True, only return properties with company owners

        Yields:
            Property objects needing enrichment
        """
        session = self.Session()
        try:
            query = session.query(Property).filter(
                Property.owner_name.isnot(None),
                Property.owner_name != ""
            )

            if company_only:
                # Filter for likely company owners
                company_patterns = [
                    '%LLC%', '%Inc%', '%Corp%', '%Trust%',
                    '%LP%', '%LLP%', '%Holdings%', '%Properties%',
                    '%Investments%', '%Realty%', '%Partners%',
                    '%Group%', '%Enterprises%', '%Company%'
                ]
                from sqlalchemy import or_
                query = query.filter(
                    or_(*[Property.owner_name.ilike(p) for p in company_patterns])
                )

            if limit:
                query = query.limit(limit)

            for prop in query:
                yield prop
        finally:
            session.close()

    def enrich_property(
        self,
        property_id: Optional[int] = None,
        parcel_id: Optional[str] = None,
        deep: bool = True
    ) -> Optional[OwnershipChain]:
        """
        Enrich a single property's owner information.

        Args:
            property_id: Database ID of the property
            parcel_id: Or the parcel ID
            deep: Whether to do deep research (multiple iterations)

        Returns:
            OwnershipChain with research findings
        """
        session = self.Session()
        try:
            # Find the property
            if property_id:
                prop = session.query(Property).filter_by(id=property_id).first()
            elif parcel_id:
                prop = session.query(Property).filter_by(parcel_id=parcel_id).first()
            else:
                logger.error("Must provide property_id or parcel_id")
                return None

            if not prop:
                logger.error(f"Property not found: {property_id or parcel_id}")
                return None

            if not prop.owner_name:
                logger.warning(f"Property {prop.parcel_id} has no owner name")
                return None

            logger.info(f"Researching owner for: {prop.address}")
            logger.info(f"Owner: {prop.owner_name}")

            # Research the owner
            if deep:
                result = self.crew.research_owner_deep(
                    owner_name=prop.owner_name,
                    property_parcel_id=prop.parcel_id,
                    property_address=prop.address or ""
                )
            else:
                result = self.crew.research_owner(
                    owner_name=prop.owner_name,
                    property_parcel_id=prop.parcel_id,
                    property_address=prop.address or ""
                )

            # Save result
            self._save_result(result)

            return result

        except Exception as e:
            logger.error(f"Error enriching property: {e}")
            raise
        finally:
            session.close()

    def enrich_batch(
        self,
        limit: int = 10,
        company_only: bool = True,
        deep: bool = False
    ) -> List[OwnershipChain]:
        """
        Enrich a batch of properties.

        Args:
            limit: Maximum number of properties to process
            company_only: Only process company owners
            deep: Whether to do deep research

        Returns:
            List of OwnershipChain results
        """
        results = []
        processed = 0

        for prop in self.get_properties_to_enrich(limit=limit, company_only=company_only):
            try:
                logger.info(f"\n{'='*60}")
                logger.info(f"Processing {processed + 1}/{limit}: {prop.address}")
                logger.info(f"Owner: {prop.owner_name}")
                logger.info('='*60)

                if deep:
                    result = self.crew.research_owner_deep(
                        owner_name=prop.owner_name,
                        property_parcel_id=prop.parcel_id,
                        property_address=prop.address or ""
                    )
                else:
                    result = self.crew.research_owner(
                        owner_name=prop.owner_name,
                        property_parcel_id=prop.parcel_id,
                        property_address=prop.address or ""
                    )

                results.append(result)
                self._save_result(result)
                processed += 1

            except Exception as e:
                logger.error(f"Error processing {prop.parcel_id}: {e}")
                continue

        logger.info(f"\nEnrichment complete. Processed {processed} properties.")
        return results

    def _save_result(self, result: OwnershipChain) -> Path:
        """Save enrichment result to JSON file."""
        filename = f"ownership_{result.property_parcel_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.output_dir / filename

        with open(filepath, 'w') as f:
            f.write(result.model_dump_json(indent=2))

        logger.info(f"Saved result to: {filepath}")
        return filepath

    def generate_report(self, results: List[OwnershipChain]) -> str:
        """
        Generate a summary report of enrichment results.

        Args:
            results: List of OwnershipChain results

        Returns:
            Markdown formatted report
        """
        report = ["# Owner Enrichment Report", ""]
        report.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"**Properties Processed:** {len(results)}")
        report.append("")

        # Summary stats
        completed = sum(1 for r in results if r.research_completed)
        with_owners = sum(1 for r in results if r.ultimate_owners)
        companies = sum(1 for r in results if r.original_owner_type in
                       [OwnerType.LLC, OwnerType.CORPORATION, OwnerType.PARTNERSHIP])

        report.append("## Summary")
        report.append(f"- Research completed: {completed}/{len(results)}")
        report.append(f"- Ultimate owners identified: {with_owners}/{len(results)}")
        report.append(f"- Corporate owners: {companies}/{len(results)}")
        report.append("")

        # Individual results
        report.append("## Property Details")
        report.append("")

        for result in results:
            report.append(f"### {result.property_address}")
            report.append(f"- **Parcel ID:** {result.property_parcel_id}")
            report.append(f"- **Original Owner:** {result.original_owner_name}")
            report.append(f"- **Owner Type:** {result.original_owner_type.value}")
            report.append("")

            if result.chain:
                report.append("**Ownership Chain:**")
                for i, link in enumerate(result.chain, 1):
                    report.append(f"{i}. {link.owner_name} ({link.owner_type.value}) - {link.relationship}")

            if result.ultimate_owners:
                report.append("")
                report.append("**Ultimate Beneficial Owners:**")
                for owner in result.ultimate_owners:
                    role = f" ({owner.role})" if owner.role else ""
                    report.append(f"- {owner.name}{role}")

            if result.errors:
                report.append("")
                report.append("**Notes:**")
                for error in result.errors:
                    report.append(f"- {error}")

            report.append("")
            report.append("---")
            report.append("")

        return "\n".join(report)


def main():
    """Command-line entry point for enrichment."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Enrich property owner information using AI agents"
    )
    parser.add_argument(
        "--parcel-id",
        help="Specific parcel ID to research"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of properties to process in batch mode"
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Perform deep research (multiple iterations)"
    )
    parser.add_argument(
        "--llm",
        default="openrouter/meta-llama/llama-3.3-70b-instruct:free",
        help="LLM model to use (default: openrouter/meta-llama/llama-3.3-70b-instruct:free)"
    )
    parser.add_argument(
        "--all-owners",
        action="store_true",
        help="Process all owners, not just companies"
    )
    parser.add_argument(
        "--db",
        default="worcester_properties.db",
        help="Path to database"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce output verbosity"
    )

    args = parser.parse_args()

    enricher = OwnerEnricher(
        db_path=args.db,
        llm=args.llm,
        verbose=not args.quiet
    )

    if args.parcel_id:
        # Single property mode
        result = enricher.enrich_property(parcel_id=args.parcel_id, deep=args.deep)
        if result:
            print("\n" + "="*60)
            print("RESULT")
            print("="*60)
            print(result.model_dump_json(indent=2))
    else:
        # Batch mode
        results = enricher.enrich_batch(
            limit=args.limit,
            company_only=not args.all_owners,
            deep=args.deep
        )

        # Generate and save report
        report = enricher.generate_report(results)
        report_path = enricher.output_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(report_path, 'w') as f:
            f.write(report)
        print(f"\nReport saved to: {report_path}")


if __name__ == "__main__":
    main()
