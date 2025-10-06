import json
from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from software_engineering.schema import ProjectSpec


@CrewBase
class EngineeringTeam():
    """Dynamic EngineeringTeam crew"""

    agents_config = 'config/agents.yaml'
    tasks_config = 'config/tasks.yaml'

    @agent
    def engineering_lead(self) -> Agent:
        return Agent(
            config=self.agents_config['engineering_lead'],
            verbose=True
        )

    @agent
    def backend_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config['backend_engineer'],
            verbose=True,
            allow_code_execution=True,
            code_execution_mode="safe",
            max_execution_time=500,
            max_retry_limit=3
        )

    @agent
    def frontend_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config['frontend_engineer'],
            verbose=True
        )

    @agent
    def test_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config['test_engineer'],
            verbose=True,
            allow_code_execution=True,
            code_execution_mode="safe",
            max_execution_time=500,
            max_retry_limit=3
        )

    @task
    def design_task(self) -> Task:
        return Task(config=self.tasks_config['design_task'])

    def build_dynamic_tasks(self, design_output: str):
        """Build tasks dynamically based on engineering lead's plan."""
        spec = ProjectSpec(**json.loads(design_output))

        tasks = []
        for module in spec.modules:
            # Backend task
            tasks.append(Task(
                description=f"Implement module {module.name} with class {module.class_name}",
                expected_output="A valid Python file implementing the class.",
                agent=self.backend_engineer(),
                output_file=f"output/{module.name}",
                inputs={
                    "module_name": module.name,
                    "class_name": module.class_name
                }
            ))

            # Test task
            tasks.append(Task(
                description=f"Write unit tests for the module {module.name}.",
                expected_output=f"A pytest-compatible test file test_{module.name}.",
                agent=self.test_engineer(),
                output_file=f"output/test_{module.name}",
                inputs={
                    "module_name": module.name,
                    "class_name": module.class_name,
                    "requirements": "Generate pytest unit tests for this class."
                }
            ))

        # Frontend task (only one per project)
        if spec.frontend:
            tasks.append(Task(
                description="Write a Gradio app (app.py) that demonstrates the backend modules.",
                expected_output="A Python Gradio UI in app.py that imports the generated backend classes.",
                agent=self.frontend_engineer(),
                output_file="output/app.py",
                inputs={
                    "requirements": "Provide a simple UI demo for all generated modules"
                }
            ))

        return tasks

    @crew
    def crew(self) -> Crew:
        """Creates the crew with just the design task initially"""
        return Crew(
            agents=self.agents,
            tasks=[self.design_task()],
            process=Process.sequential,
            verbose=True,
        )
