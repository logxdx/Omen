from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable
from agents import Agent, Tool, handoff, HandoffInputData
from agents.extensions.handoff_filters import remove_all_tools
from agents.extensions.models.litellm_model import LitellmModel

from tools.utils.history_pager import HistoryPager, Page

RECOMMENDED_PROMPT_PREFIX = ""


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
    tools: list = field(default_factory=list)

    # Context keywords for paging - defines what topics this agent cares about
    # Used during handoffs to filter relevant history pages
    context_keywords: list[str] = field(default_factory=list)

    # Maximum number of context pages to include during handoff
    max_context_pages: int = 2

    # Whether to include tool call details in handoff context
    include_tools_in_context: bool = False

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
                instructions=self.instructions + "\n" + RECOMMENDED_PROMPT_PREFIX,
                handoff_description=self.handoff_instructions,
                model=model,
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
    def _create_handoff_filter(
        target_agent: my_agent,
    ) -> Callable[[HandoffInputData], HandoffInputData]:
        """
        Create a handoff filter that uses paging for the target agent.
        The filter extracts only relevant context pages based on the target agent's keywords.
        """

        def _paged_handoff_filter(
            handoff_message_data: HandoffInputData,
        ) -> HandoffInputData:
            # Remove tool-related messages from raw history first
            # cleaned_data = remove_all_tools(handoff_message_data)
            cleaned_data = handoff_message_data

            # Convert input history to list for paging
            input_history = (
                list(cleaned_data.input_history) if cleaned_data.input_history else []
            )

            # If history is small, just pass it through
            if len(input_history) <= 3:
                return cleaned_data

            # Create pager and extract relevant context
            pager = HistoryPager(input_history)

            # Get the latest user query
            latest_query = pager.get_latest_query()

            # Build paged context for the target agent
            paged_history = pager.get_handoff_context(
                current_query=latest_query,
                target_agent_keywords=target_agent.context_keywords or None,
                max_context_pages=target_agent.max_context_pages,
                include_tools=target_agent.include_tools_in_context,
            )

            return HandoffInputData(
                input_history=tuple(paged_history),
                pre_handoff_items=tuple(cleaned_data.pre_handoff_items),
                new_items=tuple(cleaned_data.new_items),
            )

        return _paged_handoff_filter

    @staticmethod
    def _handoff_message_filter(
        handoff_message_data: HandoffInputData,
    ) -> HandoffInputData:
        """
        Default handoff filter - removes tools and passes full history.
        For paged handoffs, use _create_handoff_filter() instead.
        """
        # First, we'll remove any tool-related messages from the message history
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
                if use_paging:
                    input_filter = self._create_handoff_filter(handoff_agent)
                else:
                    input_filter = self._handoff_message_filter

                handoff_obj = handoff(agent=handoff_agent.agent, input_filter=None)
                if handoff_obj not in self.agent.handoffs:
                    self.agent.handoffs.append(handoff_obj)
