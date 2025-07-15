from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Security, Depends, Request
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
import re


import subprocess
import signal

mcp_process = None
# Load environment variables
load_dotenv()

# Global HTTP client
http_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client, mcp_process

    mcp_process = subprocess.Popen(
        ["python", "mcp/first_server.py"],  
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    http_client = AsyncClient()

    # Chờ MCP server sẵn sàng trước khi gọi tool
    await asyncio.sleep(3)

    # Gọi để lấy tool từ MCP (nếu chưa có sẵn)
    global tools
    tools = await get_mcp_tools()

    yield  

    #Cleanup khi app shutdown
    await http_client.aclose()
    if mcp_process:
        mcp_process.send_signal(signal.SIGINT)

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

# Load MCP tools
async def get_mcp_tools():
    client = MultiServerMCPClient(
        {
            "weather": {
                "url": "http://localhost:8001/mcp",
                "transport": "streamable_http",
            }
        }
    )
    tools = await client.get_tools()
    return tools

# Get model configuration for LangChain
def get_langchain_model():
    llm = os.getenv('LLM_CHOICE', 'gpt-4.1-mini')
    base_url = os.getenv('LLM_BASE_URL', 'http://localhost:11434/v1')
    api_key = os.getenv('LLM_API_KEY', 'ollama')
    return ChatOpenAI(model=llm, base_url=base_url, api_key=api_key)

# Bearer token verification
def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> bool:
    expected_token = os.getenv("BEARER_TOKEN", "").strip()
    if not expected_token:
        raise HTTPException(status_code=500, detail="BEARER_TOKEN environment variable not set or empty")
    if credentials.credentials != expected_token:
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    return True

# Database operations
async def fetch_conversation_history(session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    try:
        response = supabase.table("chat_histories").select("*").eq("session_id", session_id).limit(limit).execute()
        messages = response.data
        return messages
    except Exception as e:
        print(f"Error fetching conversation history: {e}")
        return []

async def store_message(session_id: str, message_type: str, content: str, data: Optional[Dict] = None):
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
    fastapi_request: Request,
    authenticated: bool = Depends(verify_token)
):
    try:
        agent_graph = fastapi_request.app.state.agent_graph
        metadata_agent = fastapi_request.app.state.metadata_agent

        if request.chatInput.startswith("### Task"):
            messages = [HumanMessage(content=request.chatInput)]
            result = await metadata_agent.ainvoke({"messages": messages})
            output = result["messages"][-1].content
            print(output)
            return ChatResponse(output=output)

        history = await fetch_conversation_history(request.sessionId)
        messages = []
        for msg in history:
            msg_data = msg.get("message", {})
            msg_type = msg_data.get("type")
            msg_content = msg_data.get("content", "")
            if msg_type == "human":
                messages.append(HumanMessage(content=msg_content))
            else:
                messages.append(AIMessage(content=msg_content))

        messages.append(HumanMessage(content=request.chatInput))
        await store_message(session_id=request.sessionId, message_type="human", content=request.chatInput)

        result = await agent_graph.ainvoke({"messages": messages})
        output = result["messages"][-1].content
        print(output)

        await store_message(session_id=request.sessionId, message_type="ai", content=output)
        return ChatResponse(output=output)

    except Exception as e:
        error_message = f"I encountered an error: {str(e)}"
        await store_message(session_id=request.sessionId, message_type="ai", content=error_message)
        return ChatResponse(output=error_message)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8055)
