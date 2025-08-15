#!/usr/bin/env python3
"""
Generate comprehensive review reports from all agents
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from agents import agent_coordinator

def main():
    """Generate all review reports."""
    print("AI Generating comprehensive review from all agents...")
    print("=" * 60)
    
    # Get detailed reports
    reports = agent_coordinator.get_detailed_reports()
    
    # Create reports directory
    reports_dir = project_root / "reports"
    reports_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save executive summary
    exec_summary_file = reports_dir / f"executive_summary_{timestamp}.md"
    with open(exec_summary_file, 'w', encoding='utf-8') as f:
        f.write(reports["executive_summary"])
    print(f"Executive Summary saved to: {exec_summary_file}")
    
    # Save project management report
    pm_report_file = reports_dir / f"project_management_report_{timestamp}.md"
    with open(pm_report_file, 'w', encoding='utf-8') as f:
        f.write(reports["project_management_report"])
    print(f"Project Management Report saved to: {pm_report_file}")
    
    # Save product requirements document
    prd_file = reports_dir / f"product_requirements_document_{timestamp}.md"
    with open(prd_file, 'w', encoding='utf-8') as f:
        f.write(reports["product_requirements_document"])
    print(f"Product Requirements Document saved to: {prd_file}")
    
    # Save QA testing report
    qa_report_file = reports_dir / f"qa_testing_report_{timestamp}.md"
    with open(qa_report_file, 'w', encoding='utf-8') as f:
        f.write(reports["qa_testing_report"])
    print(f"QA Testing Report saved to: {qa_report_file}")
    
    print("\n" + "=" * 60)
    print("All reports generated successfully!")
    print("\nQUICK SUMMARY:")
    
    # Display executive summary in console
    print(reports["executive_summary"])

if __name__ == "__main__":
    main()