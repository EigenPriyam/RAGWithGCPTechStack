from langchain_groq import ChatGroq
from src.rag_agent.state import AgentState
from src.config import settings
import logfire
from pydantic import BaseModel
from typing import Literal , Optional

class PlannerDecision(BaseModel):
      intent: Literal["conversational", "technical"]
      search_query: Optional[str] = None  # only populated when intent == "technical"
    
# Initialize the Groq model
llm = ChatGroq(
    api_key=settings.GROQ_API_KEY,
    model=settings.GROQ_MODEL,
    temperature=0
)

llm_structured = llm.with_structured_output(PlannerDecision)

def planner_node(state: AgentState):
    """
    The Planner determines if a search is needed based on the ENTIRE conversation.
    """
    # Get the conversation history (excluding the latest message)
    history = ""
    for msg in state["messages"][:-1]:
        role = "User" if msg["role"] == "user" else "Assistant"
        history += f"{role}: {msg['content']}\n"
    
    user_message = state["messages"][-1]["content"] if state["messages"] else ""
    
    prompt = f"""
    You are an intelligent Assistant Planner.
    Analyze the conversation history and the latest user message.

    CONVERSATION HISTORY:
    {history}

    LATEST MESSAGE:
    "{user_message}"

    Task:
    1. If the latest message is a greeting (hi, hello) or a question answerable from conversation history alone, set intent to 'conversational' and leave search_query empty.
    2. If it is a technical question about Kubernetes, Intel, or Networking requiring fresh documentation, set intent to 'technical' and provide a refined search_query.
    """
    
    with logfire.span("🧠 Planner Decision"):
        decision = llm_structured.invoke(prompt)
        query_intent = decision.intent
        search_query = decision.search_query if decision.intent == "technical" else ""
        logfire.info(f"Intent identified: {query_intent}")
        if search_query:
            logfire.info(f"Search query generated: {search_query}")
        
    if query_intent == "conversational":
        return {
            "current_query": "conversational",
            "status": "Handling conversationally (using memory)...",
            "plan": ["Intent: Conversational/Memory", "Retrieval: Skipped"]
        }
    
    return {
        "current_query": search_query,
        "status": f"Technical research needed. Searching for: {search_query}",
        "plan": [f"Intent: {query_intent}, Search Term: {search_query}"]
    }
