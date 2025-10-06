#!/usr/bin/env python
import os
from software_engineering.crew import EngineeringTeam


# Requirements for the project
requirements = """
A trading simulation platform account system.
- Create accounts, deposit, withdraw.
- Record buy/sell shares with quantity.
- Portfolio valuation and P/L calculation.
- Holdings and transaction history.
- Prevent invalid operations.
- Use get_share_price(symbol) with test prices for AAPL, TSLA, GOOGL.
- Provide a simple frontend to demonstrate functionality.
"""

def run():
    os.makedirs('output', exist_ok=True)

    inputs = {"requirements": requirements}

    team = EngineeringTeam()

    # Run the design step
    design_result = team.crew().kickoff(inputs=inputs)
    with open("output/project_plan.json") as f:
        design_output = f.read()

    # Build and run dynamic tasks (backend, tests, frontend)
    dynamic_tasks = team.build_dynamic_tasks(design_output)
    dynamic_crew = team.crew()
    dynamic_crew.tasks.extend(dynamic_tasks)
    dynamic_crew.kickoff(inputs=inputs)
