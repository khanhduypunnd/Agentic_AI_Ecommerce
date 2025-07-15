from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from supabase import create_client, Client
from pydantic import BaseModel
from dataclasses import dataclass
from dotenv import load_dotenv
from httpx import AsyncClient
import os
import json
import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient

# LangGraph and LangChain imports
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from prompts import system_prompt
from langchain_core.messages import HumanMessage, AIMessage
import torch
from retriever.retrieval import query_supabase, get_product_semantic
from langchain_community.embeddings import HuggingFaceEmbeddings
# Load environment variables
load_dotenv()

# Global HTTP client
http_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global http_client
    http_client = AsyncClient()

    yield

    # Shutdown
    await http_client.aclose()

# Initialize FastAPI app with lifespan
app = FastAPI(lifespan=lifespan)
security = HTTPBearer()

# Supabase setup
supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_KEY")
)


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response Models
class ChatRequest(BaseModel):
    chatInput: str
    sessionId: str

class ChatResponse(BaseModel):
    output: str

# Agent dependencies
@dataclass
class AgentDeps:
    http_client: AsyncClient
    searxng_base_url: str

# LangGraph agent setup
    
# Load MCP tools

async def get_mcp_tools():
    client = MultiServerMCPClient(
        {
            # "math":{
            #     "command":"python",
            #     "args":["first_server.py"], ## Ensure correct absolute path
            #     "transport":"stdio",
            # },
            "weather": {
                "url": "http://localhost:8001/mcp",  # Ensure server is running here
                "transport": "streamable_http",
            }
        }
    )

    tools = await client.get_tools()
    return tools

tools = asyncio.run(get_mcp_tools())

embedding_model = HuggingFaceEmbeddings(
    model_name="Alibaba-NLP/gte-multilingual-base",
    model_kwargs={'device':'cuda' if torch.cuda.is_available() else 'cpu', 'trust_remote_code': True}
)

def get_product_semantic_tool(query: str) -> str:
    """
    Return a semantic information string of products based on a query.

    Args:
        query (str): The search query to find relevant products.

    Returns:
        str: A formatted string summarizing the total number of products found
             and their metadata details.
    """
    return get_product_semantic(query, embedding_model=embedding_model)

# Get model configuration for LangChain
def get_langchain_model():
    llm = os.getenv('LLM_CHOICE', 'gpt-4.1-mini')
    base_url = os.getenv('LLM_BASE_URL', 'http://localhost:11434/v1')
    api_key = os.getenv('LLM_API_KEY', 'ollama')
    return ChatOpenAI(model=llm, base_url=base_url, api_key=api_key)

llm = get_langchain_model()

# Use create_react_agent for a clean agent setup
agent_graph = create_react_agent(
    model=llm,
    tools=[get_product_semantic_tool, query_supabase, *tools],
    prompt=system_prompt
)

metadata_agent = create_react_agent(
    model=llm,
    tools=[],
    prompt="You are a helpful assistant."
)

# Bearer token verification
def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> bool:
    """Verify the bearer token against environment variable."""
    expected_token = os.getenv("BEARER_TOKEN")
    if not expected_token:
        raise HTTPException(
            status_code=500,
            detail="BEARER_TOKEN environment variable not set"
        )
    
    # Ensure the token is not empty or just whitespace
    expected_token = expected_token.strip()
    if not expected_token:
        raise HTTPException(
            status_code=500,
            detail="BEARER_TOKEN environment variable is empty"
        )
    
    if credentials.credentials != expected_token:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token"
        )
    return True

# Database operations
async def fetch_conversation_history(session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Fetch conversation history from Supabase."""
    try:
        response = supabase.table("chat_histories") \
            .select("*") \
            .eq("session_id", session_id) \
            .limit(limit) \
            .execute()
        
        # Reverse to get chronological order
        messages = response.data
        return messages
    except Exception as e:
        print(f"Error fetching conversation history: {e}")
        return []

import re

async def store_message(session_id: str, message_type: str, content: str, data: Optional[Dict] = None):
    """Store a message in Supabase, removing <think>...</think> blocks from content."""
    # Remove <think>...</think> blocks (including multiline)
    cleaned_content = re.sub(r'<think>.*?</think>\s*', '', content, flags=re.DOTALL | re.IGNORECASE)
    message_obj = {
        "type": message_type,
        "content": cleaned_content.strip()
    }
    if data:
        message_obj["data"] = data
    try:
        supabase.table("chat_histories").insert({
            "session_id": session_id,
            "message": message_obj
        }).execute()
    except Exception as e:
        print(f"Error storing message: {e}")

# Main endpoint
@app.post("/invoke-python-agent", response_model=ChatResponse)
async def invoke_agent(
    request: ChatRequest,
    authenticated: bool = Depends(verify_token)
):
    """Main endpoint that handles chat requests with web search capability using LangGraph agent."""
    # Check if this is a metadata request (starting with "### Task")
    if request.chatInput.startswith("### Task"):
        # For metadata requests, use the metadata agent without history
        messeges = [
            HumanMessage(content=request.chatInput)
        ]
        result = await metadata_agent.ainvoke({"messages": messeges})
        print(result["messages"][-1].content)
        return ChatResponse(output=result["messages"][-1].content)
    
    try:
        # Fetch conversation history
        history = await fetch_conversation_history(request.sessionId)
        messages = []
        for msg in history:  # Đảm bảo thứ tự từ cũ đến mới
            msg_data = msg.get("message", {})
            msg_type = msg_data.get("type")
            msg_content = msg_data.get("content", "")
            if msg_type == "human":
                messages.append(HumanMessage(content=msg_content))
            else:
                messages.append(AIMessage(content=msg_content))

        # Thêm input mới nhất của user vào messages
        messages.append(HumanMessage(content=request.chatInput))

        # Store user's message
        await store_message(
            session_id=request.sessionId,
            message_type="human",
            content=request.chatInput
        )
    
        # Run LangGraph agent
        result = await agent_graph.ainvoke(
            {"messages": messages},
        )
        output = result["messages"][-1].content
        print(output)
        
        # Store agent's response
        await store_message(
            session_id=request.sessionId,
            message_type="ai",
            content=output
        )
        
        return ChatResponse(output=output)
    except Exception as e:
        error_message = f"I encountered an error: {str(e)}"
        
        # Store error response
        await store_message(
            session_id=request.sessionId,
            message_type="ai",
            content=error_message
        )
        
        return ChatResponse(output=error_message)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8055)