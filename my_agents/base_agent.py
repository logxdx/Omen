from __future__ import annotations

from dataclasses import dataclass, field
from agents import Agent, Tool, handoff, HandoffInputData, ModelSettings
from agents.extensions.handoff_filters import remove_all_tools
from agents.extensions.models.litellm_model import LitellmModel

from config.agent_config import MAX_TURNS

# =============================================================================
# HANDOFFS vs AGENT-AS-TOOLS
# =============================================================================
#
# HANDOFFS:
#   - Transfers COMPLETE conversation history to the new agent
#   - New agent takes over the conversation entirely
#   - Original agent loses control; user now talks to the new agent
#   - Use when: task requires full context and agent specialization
#   - Example: Triage → Specialist (specialist needs all prior discussion)
#
# AGENT-AS-TOOLS (Sub-agents):
#   - Executes a specific task and returns ONLY the final answer
#   - Original agent stays in control of the conversation
#   - Sub-agent doesn't see full history, just the delegated task
#   - Use when: need a specialized result without losing conversation control
#   - Example: Main agent calls research sub-agent, gets summary back
#
# TL;DR:
#   Handoff  = "You take over" (full context transfer, control shifts)
#   As-Tool  = "Do this for me" (task delegation, get result back)
#
# =============================================================================

RECOMMENDED_PROMPT_PREFIX = ""


@dataclass
class agent_config:
    BASE_URL: str
    API_KEY: str
    MODEL_NAME: str


@dataclass
class my_agent:

    agent_name: str
    instructions: str
    config: agent_config
    agent: Agent = None  # type: ignore
    handoff_instructions: str = ""
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
                instructions=(
                    self.instructions
                    + (
                        ("\n" + RECOMMENDED_PROMPT_PREFIX)
                        if RECOMMENDED_PROMPT_PREFIX
                        else ""
                    )
                ),
                handoff_description=self.handoff_instructions,
                model=model,
                model_settings=ModelSettings(include_usage=True),
                tools=self.tools,
            )

    def add_tools(self, tools: list[Tool] | Tool):
        """
        Add tools to this agent's tool list
        """
        if not self.agent:
            raise ValueError("Agent not created yet. Call create_agent() first.")
        if not isinstance(tools, list):
            tools = [tools]
        self.tools.extend(tools)
        for tool in self.tools:
            if tool not in self.agent.tools:
                self.agent.tools.append(tool)

    @staticmethod
    def _handoff_message_filter(
        handoff_message_data: HandoffInputData,
    ) -> HandoffInputData:
        """
        Default handoff filter - removes tools and passes full history.
        For paged handoffs, use _create_handoff_filter() instead.
        """
        # We'll remove any tool-related messages from the message history
        handoff_message_data = remove_all_tools(handoff_message_data)

        # or, you can use the HandoffInputData.clone(kwargs) method
        return HandoffInputData(
            input_history=handoff_message_data.input_history,
            pre_handoff_items=tuple(handoff_message_data.pre_handoff_items),
            new_items=tuple(handoff_message_data.new_items),
        )

    def add_handoffs(
        self, handoffs: list[my_agent] | my_agent, use_paging: bool = False
    ):
        """
        Add handoff agents to this agent's handoff list
        and update instructions to include their handoff_instructions.

        Args:
            handoffs: Agent(s) to add as handoff targets
            use_paging: If True, use paged context filtering during handoffs.
                        If False, pass full history (legacy behavior).
        """

        if not self.agent:
            raise ValueError("Agent not created yet. Call create_agent() first.")
        if not isinstance(handoffs, list):
            handoffs = [handoffs]
        if handoffs:
            for handoff_agent in handoffs:
                # Create appropriate filter based on paging preference

                handoff_obj = handoff(agent=handoff_agent.agent, input_filter=None)
                if handoff_obj not in self.agent.handoffs:
                    self.agent.handoffs.append(handoff_obj)

    def add_subagents(self, subagents: list[my_agent] | my_agent):
        """
        Add sub-agent tools to this agent's tool list.
        Sub-agents are used as tools within the main agent's conversation.

        Args:
            subagents: Agent(s) to add as sub-agent tools
        """

        if not self.agent:
            raise ValueError("Agent not created yet. Call create_agent() first.")
        if not isinstance(subagents, list):
            subagents = [subagents]
        if subagents:
            for subagent in subagents:
                self.agent.tools.append(
                    subagent.agent.as_tool(
                        tool_name=f"ask_{subagent.agent_name.lower().replace(' ', '_')}",
                        tool_description=(
                            f"Sub-agent for: {subagent.handoff_instructions}. "
                            f"Send a task, get back relevant context."
                        ),
                        max_turns=MAX_TURNS,
                    )
                )
