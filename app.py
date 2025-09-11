import streamlit as st
import asyncio
from typing import List, Dict, Any
from agents import (
    RawResponsesStreamEvent,
    Runner,
    RunItemStreamEvent,
    TResponseInputItem,
    set_tracing_disabled,
)
from agents import Agent
from openai.types.responses import ResponseTextDeltaEvent
from config.agent_config import MAX_TURNS

# Disable tracing
set_tracing_disabled(disabled=True)

# Agent Definitions
from my_agents.ideation_agent import create_ideation_agent
from my_agents.web_search_agent import create_web_search_agent
from my_agents.filesystem_agent import create_filesystem_agent
from my_agents.triage_agent import create_triage_agent

# Create agents
ideation_agent = create_ideation_agent()
web_search_agent = create_web_search_agent()
filesystem_agent = create_filesystem_agent()
triage_agent = create_triage_agent(handoffs=[web_search_agent, filesystem_agent])

# Add mesh handoffs to all agents
ideation_agent.handoffs.extend([triage_agent, web_search_agent, filesystem_agent])
web_search_agent.handoffs.extend([triage_agent, filesystem_agent])
filesystem_agent.handoffs.extend([triage_agent, web_search_agent])

# Agent registry
agents: Dict[str, Agent] = {
    "triage": triage_agent,
    "web": web_search_agent,
    "fs": filesystem_agent,
    "idea": ideation_agent,
}

display_names: Dict[str, str] = {
    "triage": "Triage Agent",
    "web": "Web Search Agent",
    "fs": "Filesystem Agent",
    "idea": "Ideation Agent",
}

def init_session_state():
    """Initialize session state variables."""
    if 'hierarchy_mode' not in st.session_state:
        st.session_state.hierarchy_mode = None
    if 'current_agent_key' not in st.session_state:
        st.session_state.current_agent_key = "triage"
    if 'conversation_history' not in st.session_state:
        st.session_state.conversation_history = []
    if 'agent_intro_shown' not in st.session_state:
        st.session_state.agent_intro_shown = False

def display_welcome():
    """Display welcome panel."""
    st.title("🤖 Multi-Agent Assistant")
    st.markdown("### Version 1.0.0")
    st.markdown("**I can help you with:**")
    st.markdown("- 🔍 Web searches")
    st.markdown("- 📁 File operations")
    st.markdown("- 💡 Brainstorming and ideation")
    st.markdown("**Commands:**")
    st.markdown("- `/agents` or `/a` - List and switch agents")
    st.markdown("- `/clear` or `/c` - Clear conversation")
    st.markdown("- `/quit` or `/q` - Exit (refresh page)")

def choose_hierarchy_mode():
    """Prompt user to choose hierarchy mode."""
    st.markdown("### Choose your preferred interaction mode:")
    st.markdown("1. **Collaborative** - Agents can handoff directly to each other")
    st.markdown("2. **Managerial** - Triage agent manages all interactions behind the scenes")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Collaborative", key="collab"):
            st.session_state.hierarchy_mode = "collaborative"
            st.success("✅ Collaborative mode selected!")
            st.rerun()
    with col2:
        if st.button("Managerial", key="manager"):
            st.session_state.hierarchy_mode = "managerial"
            st.success("✅ Managerial mode selected!")
            st.rerun()

async def generate_agent_intro(agent: Agent):
    """Generate dynamic introduction by running the agent."""
    inputs: List[TResponseInputItem] = [
        {
            "content": "Introduce yourself very-briefly and ask for the user's needs.",
            "role": "user",
        }
    ]
    result = Runner.run_streamed(
        starting_agent=agent, input=inputs, max_turns=MAX_TURNS
    )
    
    full_response = ""
    events = []
    
    async for event in result.stream_events():
        if isinstance(event, RawResponsesStreamEvent):
            data = event.data
            if isinstance(data, ResponseTextDeltaEvent):
                delta = data.delta
                if "<think>" in delta or "</think>" in delta:
                    # Handle thinking tags
                    continue
                full_response += delta
        elif isinstance(event, RunItemStreamEvent):
            if event.name == "handoff_requested":
                target_name = getattr(event.item.raw_item, "name", "another agent")
                events.append(f"🔄 Handoff requested to {target_name}")
            elif event.name == "handoff_occured":
                target_name = event.item.target_agent.name # type: ignore
                events.append(f"✅ Handoff completed to {target_name}")
    
    return full_response, events

def display_events(events: List[str]):
    """Display events in a sidebar or expander."""
    if events:
        with st.expander("Events", expanded=False):
            for event in events:
                st.write(event)

async def stream_agent_response(agent: Agent, inputs: List[TResponseInputItem], hierarchy_mode: str):
    """Stream the agent's response and handle events."""
    result = Runner.run_streamed(
        starting_agent=agent, input=inputs, max_turns=MAX_TURNS
    )
    
    full_response = ""
    events = []
    response_placeholder = st.empty()
    events_placeholder = st.empty()
    
    async for event in result.stream_events():
        if isinstance(event, RawResponsesStreamEvent):
            data = event.data
            if isinstance(data, ResponseTextDeltaEvent):
                delta = data.delta
                if "<think>" in delta or "</think>" in delta:
                    continue
                full_response += delta
                response_placeholder.markdown(full_response)
        elif isinstance(event, RunItemStreamEvent):
            if event.name == "handoff_requested":
                target_name = getattr(event.item.raw_item, "name", "another agent")
                display_target = display_names.get(target_name.replace("_agent", ""), target_name)
                events.append(f"🔄 Handoff requested to {display_target}")
            elif event.name == "handoff_occured":
                target_name = event.item.target_agent.name # type: ignore
                display_target = display_names.get(target_name.replace("_agent", ""), target_name)
                if hierarchy_mode == "collaborative":
                    st.session_state.current_agent_key = target_name.replace("_agent", "")
                    events.append(f"✅ Handoff completed to {display_target}")
                else:
                    events.append(f"🔄 Task delegated to {display_target}")
            elif event.name == "tool_called":
                tool_name = getattr(event.item.raw_item, "name", "unknown tool")
                events.append(f"🛠️ Tool called: {tool_name}")
            elif event.name == "tool_output":
                events.append("📤 Tool output received")
            elif event.name == "reasoning_item_created":
                events.append("🤔 Reasoning in progress")
            
            events_placeholder.markdown("\n".join(events))
    
    # Add the agent's response to conversation history
    if full_response:
        inputs.append({"content": full_response, "role": "assistant"})
    
    return inputs, events

def handle_agents_command(command: str):
    """Handle /agents command."""
    parts = command.split()
    if len(parts) == 1:
        st.markdown("**Available Agents:**")
        for key, name in display_names.items():
            st.write(f"- {key}: {name}")
        st.write("Use `/agents <name>` to switch agents.")
    elif len(parts) == 2:
        agent_key = parts[1].lower()
        if agent_key in agents:
            st.session_state.current_agent_key = agent_key
            st.success(f"Switched to {display_names[agent_key]}")
        else:
            st.error(f"Unknown agent: {agent_key}")

def handle_clear_command():
    """Handle /clear command."""
    st.session_state.conversation_history = []
    st.session_state.agent_intro_shown = False
    st.success("🔄 Conversation cleared!")

def main():
    st.set_page_config(page_title="Multi-Agent Assistant", page_icon="🤖", layout="wide")
    
    init_session_state()
    
    # Sidebar for agent selection
    with st.sidebar:
        st.header("Agent Control")
        current_agent = agents[st.session_state.current_agent_key]
        st.write(f"**Current Agent:** {display_names[st.session_state.current_agent_key]}")
        
        # Agent switcher
        new_agent = st.selectbox(
            "Switch Agent:",
            options=list(display_names.keys()),
            index=list(display_names.keys()).index(st.session_state.current_agent_key),
            format_func=lambda x: display_names[x]
        )
        if new_agent != st.session_state.current_agent_key:
            st.session_state.current_agent_key = new_agent
            st.session_state.agent_intro_shown = False
            st.rerun()
        
        # Mode display
        if st.session_state.hierarchy_mode:
            st.write(f"**Mode:** {st.session_state.hierarchy_mode.capitalize()}")
        
        # Clear conversation
        if st.button("Clear Conversation"):
            handle_clear_command()
            st.rerun()
    
    # Main content
    display_welcome()
    
    if not st.session_state.hierarchy_mode:
        choose_hierarchy_mode()
        return
    
    # Show agent intro if not shown
    if not st.session_state.agent_intro_shown:
        with st.spinner("Generating agent introduction..."):
            intro_response, intro_events = asyncio.run(generate_agent_intro(current_agent))
        st.markdown("### Agent Introduction")
        st.markdown(intro_response)
        display_events(intro_events)
        st.session_state.agent_intro_shown = True
    
    # Chat interface
    st.markdown("---")
    st.markdown("### Conversation")
    
    # Display conversation history
    for msg in st.session_state.conversation_history:
        if msg["role"] == "user":
            st.markdown(f"**You:** {msg['content']}")
        elif msg["role"] == "assistant":
            st.markdown(f"**{display_names[st.session_state.current_agent_key]}:** {msg['content']}")
            # Display events if any
            if 'events' in msg:
                display_events(msg['events'])
    
    # User input
    user_input = st.text_input("Your message:", key="user_input")
    
    if st.button("Send") and user_input:
        # Handle commands
        if user_input.lower().startswith("/a") or user_input.lower().startswith("/agents"):
            handle_agents_command(user_input)
        elif user_input.lower().startswith("/c") or user_input.lower().startswith("/clear"):
            handle_clear_command()
        elif user_input.lower() in ["/q", "/quit", "/exit"]:
            st.info("Refresh the page to exit.")
        else:
            # Add to conversation
            st.session_state.conversation_history.append({"content": user_input, "role": "user"})
            
            # Stream response
            with st.spinner("Agent is responding..."):
                updated_inputs, response_events = asyncio.run(stream_agent_response(
                    current_agent, 
                    st.session_state.conversation_history, 
                    st.session_state.hierarchy_mode
                ))
            
            # Update conversation history
            st.session_state.conversation_history = updated_inputs
            
            # Display events for the latest response
            if response_events:
                display_events(response_events)
        
        st.rerun()

if __name__ == "__main__":
    main()