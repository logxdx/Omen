from __future__ import annotations
from dataclasses import dataclass, field
from agents import Agent, Tool
from agents.extensions.models.litellm_model import LitellmModel


@dataclass
class agent_config:
    BASE_URL: str
    API_KEY: str
    MODEL_NAME: str


@dataclass
class my_agent:

    agent_name: str
    config: agent_config
    instructions: str
    agent: Agent = None  # type: ignore
    handoff_instructions: str = ""
    handoffs: list[my_agent] = field(default_factory=list)
    tools: list = field(default_factory=list)

    def __post_init__(self):
        self.create_agent()

    def create_agent(self):
        """
        Create the agent instance if not already created
        and set up the model with the provided configuration
        """

        model = LitellmModel(
            model=self.config.MODEL_NAME,
            api_key=self.config.API_KEY,
            base_url=self.config.BASE_URL,
        )

        if not self.agent:
            self.agent = Agent(
                name=self.agent_name,
                instructions=self.instructions,
                model=model,
                tools=self.tools,
            )

    def add_tools(self, tools: list[Tool] | Tool):
        """
        Add tools to this agent's tool list
        """
        if not self.agent:
            raise ValueError("Agent not created yet. Call create_agent() first.")
        if isinstance(tools, Tool):
            tools = [tools]
        self.tools.extend(tools)
        for tool in self.tools:
            if tool not in self.agent.tools:
                self.agent.tools.append(tool)

    def add_handoffs(self, handoffs: list[my_agent] | my_agent):
        """
        Add handoff agents to this agent's handoff list
        and update instructions to include their handoff_instructions
        """

        if not self.agent:
            raise ValueError("Agent not created yet. Call create_agent() first.")
        if isinstance(handoffs, my_agent):
            handoffs = [handoffs]
        if handoffs:
            if not self.handoffs:
                self.instructions += "\n\n## AVAILABLE SPECIALIST AGENTS\n---\n"
            self.handoffs.extend(handoffs)
            for handoff_agent in self.handoffs:
                if (
                    handoff_agent.agent
                    and handoff_agent.agent not in self.agent.handoffs
                ):
                    self.agent.handoffs.append(handoff_agent.agent)
                    self.instructions += f"\n{handoff_agent.handoff_instructions}\n"
        self.agent.instructions = self.instructions
