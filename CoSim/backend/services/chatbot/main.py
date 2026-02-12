"""
CoSim RAG Chatbot Service
Provides intelligent Q&A about the product using RAG retrieval
"""
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import openai
import ollama
import replicate

from vector_store import RAGVectorStore, initialize_vector_store
from redis_cache import append_history, fetch_history


# Global vector store instance
vector_store: Optional[RAGVectorStore] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize vector store on startup"""
    global vector_store
    print("🚀 Starting CoSim Chatbot Service...")
    vector_store = initialize_vector_store()
    yield
    print("👋 Shutting down CoSim Chatbot Service...")


app = FastAPI(
    title="CoSim Chatbot API",
    description="RAG-powered Q&A chatbot for CoSim product information",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models
class ChatMessage(BaseModel):
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatRequest(BaseModel):
    message: str = Field(..., description="User's question")
    conversation_history: List[ChatMessage] = Field(
        default_factory=list,
        description="Previous conversation messages for context"
    )
    max_history: int = Field(
        default=5,
        description="Maximum number of previous messages to include"
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="Optional conversation identifier for Redis-backed history"
    )


class ChatResponse(BaseModel):
    response: str = Field(..., description="Chatbot's answer")
    sources: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Source documents used for the answer"
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class HealthResponse(BaseModel):
    status: str
    vector_store_stats: Dict[str, Any]


# Dependency to get vector store
def get_vector_store() -> RAGVectorStore:
    """Dependency to get the vector store instance"""
    if vector_store is None:
        raise HTTPException(status_code=503, detail="Vector store not initialized")
    return vector_store


def generate_response_with_context(
    query: str,
    context_docs: List[Dict[str, Any]],
    conversation_history: List[ChatMessage] = None
) -> str:
    """
    Generate a response using RAG context
    This is a simple implementation without external LLM API
    For production, integrate with OpenAI or a local LLM
    """
    # Format context from retrieved documents
    context_text = "\n\n".join([
        f"[Source: {doc['metadata'].get('section', 'Unknown')}]\n{doc['content']}"
        for doc in context_docs
    ])
    
    # For now, return a simple response with context
    # In production, you would call OpenAI or another LLM here
    
    # Check if we have good context
    if not context_docs:
        return ("I don't have specific information about that in my knowledge base. "
                "Could you rephrase your question or ask about CoSim's features, "
                "pricing, simulators, or how to get started?")
    
    # Extract the most relevant piece
    best_match = context_docs[0]
    
    # Simple response generation (replace with LLM in production)
    response = f"Based on our documentation:\n\n{best_match['content']}\n\n"
    
    # Add a helpful closing
    if best_match['metadata'].get('section') == 'FAQ':
        response += "Is there anything else you'd like to know about CoSim?"
    else:
        response += f"This information is from the '{best_match['metadata'].get('section', 'documentation')}' section. Would you like more details?"
    
    return response


def generate_llm_response(
    query: str,
    context_docs: List[Dict[str, Any]],
    conversation_history: List[ChatMessage] = None
) -> str:
    """
    Generate response using Ollama or OpenAI
    Tries Ollama first (local), falls back to OpenAI if configured
    """
    # --- NEW: Try Replicate first for cloud deployments ---
    replicate_api_token = os.getenv("REPLICATE_API_TOKEN")
    if replicate_api_token:
        print(f"🤖 Attempting to generate response using Replicate...")
        try:
            # Llama 3.1 8B Instruct model on Replicate
            model_version = "meta/meta-llama-3.1-8b-instruct:63af552585433a13f5939888659445c2a7da55c8055284d4356a336053852005"
            response = generate_replicate_response(query, context_docs, conversation_history, model_version)
            print(f"✅ Successfully generated response using Replicate!")
            return response
        except Exception as e:
            print(f"❌ Replicate failed: {e}, trying other options...")


    # Try Ollama first (local LLM)
    ollama_host = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2")
    
    print(f"🤖 Attempting to generate response using Ollama ({ollama_model}) at {ollama_host}")
    try:
        response = generate_ollama_response(query, context_docs, conversation_history, ollama_host, ollama_model)
        print(f"✅ Successfully generated response using Ollama!")
        return response
    except Exception as e:
        print(f"❌ Ollama failed: {e}, trying OpenAI...")
    
    # Try OpenAI if Ollama fails
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        print(f"🤖 Attempting to generate response using OpenAI...")
        try:
            response = generate_openai_response(query, context_docs, conversation_history, api_key)
            print(f"✅ Successfully generated response using OpenAI!")
            return response
        except Exception as e:
            print(f"❌ OpenAI failed: {e}")
    
    # Fall back to simple context-based response
    print(f"⚠️  Falling back to simple context-based response")
    return generate_response_with_context(query, context_docs, conversation_history)
def generate_ollama_response(
    query: str,
    context_docs: List[Dict[str, Any]],
    conversation_history: List[ChatMessage] = None,
    host: str = "http://localhost:11434",
    model: str = "llama3.2"
) -> str:
    """
    Generate response using Ollama (local LLM)
    """
    # Format context
    context_text = "\n\n".join([
        f"Source [{doc['metadata'].get('section', 'Unknown')}]:\n{doc['content']}"
        for doc in context_docs
    ])
    
    # Build conversation history
    messages = []
    
    # System prompt
    system_prompt = (
        "You are a helpful assistant for CoSim, a cloud-based collaborative "
        "robotics development platform. Answer questions about CoSim's features, "
        "capabilities, pricing, and how to use it. Use the provided context to "
        "give accurate answers. Be concise but informative. If you don't know "
        "something, say so politely."
    )
    
    # Add conversation history (last N messages)
    if conversation_history:
        for msg in conversation_history[-5:]:  # Last 5 messages
            messages.append({
                "role": msg.role,
                "content": msg.content
            })
    
    # Build the final prompt with context
    user_prompt = f"Context:\n{context_text}\n\nQuestion: {query}"
    
    # Call Ollama API
    client = ollama.Client(host=host)
    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            *messages,
            {"role": "user", "content": user_prompt}
        ],
        options={
            "temperature": 0.7,
            "num_predict": 500
        }
    )
    
    return response['message']['content']


def generate_replicate_response(
    query: str,
    context_docs: List[Dict[str, Any]],
    conversation_history: List[ChatMessage] = None,
    model_version: str = "meta/meta-llama-3.1-8b-instruct:63af552585433a13f5939888659445c2a7da55c8055284d4356a336053852005"
) -> str:
    """
    Generate response using a serverless model host like Replicate.
    """
    # Format context
    context_text = "\n\n".join([
        f"Source [{doc['metadata'].get('section', 'Unknown')}]:\n{doc['content']}"
        for doc in context_docs
    ])

    # Build conversation history for the prompt
    messages = []
    system_prompt = (
        "You are a helpful assistant for CoSim, a cloud-based collaborative "
        "robotics development platform. Answer questions about CoSim's features, "
        "capabilities, pricing, and how to use it. Use the provided context to "
        "give accurate answers. Be concise but informative. If you don't know "
        "something, say so politely."
    )
    messages.append({"role": "system", "content": system_prompt})

    if conversation_history:
        for msg in conversation_history[-5:]:  # Last 5 messages
            messages.append({"role": msg.role, "content": msg.content})

    # Add context and current query
    user_prompt = f"Context:\n{context_text}\n\nQuestion: {query}"
    messages.append({"role": "user", "content": user_prompt})

    # Call Replicate API
    output = replicate.run(
        model_version,
        input={"messages": messages}
    )

    # The output is an iterator, concatenate it to get the full response
    response_text = "".join(list(output))

    return response_text


def generate_openai_response(
    query: str,
    context_docs: List[Dict[str, Any]],
    conversation_history: List[ChatMessage] = None,
    api_key: str = None
) -> str:
    """
    Generate response using OpenAI (fallback option)
    """
    try:
        # Set up OpenAI client
        client = openai.OpenAI(api_key=api_key)
        
        # Format context
        context_text = "\n\n".join([
            f"Source [{doc['metadata'].get('section', 'Unknown')}]:\n{doc['content']}"
            for doc in context_docs
        ])
        
        # Build conversation history
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant for CoSim, a cloud-based collaborative "
                    "robotics development platform. Answer questions about CoSim's features, "
                    "capabilities, pricing, and how to use it. Use the provided context to "
                    "give accurate answers. Be concise but informative. If you don't know "
                    "something, say so politely."
                )
            }
        ]
        
        # Add conversation history (last N messages)
        if conversation_history:
            for msg in conversation_history[-5:]:  # Last 5 messages
                messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
        
        # Add context and current query
        messages.append({
            "role": "user",
            "content": f"Context:\n{context_text}\n\nQuestion: {query}"
        })
        
        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )
        
        return response.choices[0].message.content
    
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        # Fall back to simple response
        return generate_response_with_context(query, context_docs, conversation_history)


@app.get("/", response_model=Dict[str, str])
async def root():
    """Root endpoint"""
    return {
        "service": "CoSim Chatbot API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check(store: RAGVectorStore = Depends(get_vector_store)):
    """Health check endpoint"""
    stats = store.get_stats()
    return HealthResponse(
        status="healthy",
        vector_store_stats=stats
    )


@app.post("/chat/query", response_model=ChatResponse)
async def chat_query(
    request: ChatRequest,
    store: RAGVectorStore = Depends(get_vector_store)
):
    """
    Process a chat query using RAG retrieval
    """
    try:
        history: List[ChatMessage] = []
        if request.conversation_id:
            stored_entries = fetch_history(
                request.conversation_id,
                limit=request.max_history * 2,
            )
            history.extend(ChatMessage.model_validate(entry) for entry in stored_entries)

        history.extend(request.conversation_history[-request.max_history :])

        # Query vector store for relevant context
        retrieved_docs = store.query(request.message, n_results=5)

        # Generate response using context
        # Try LLM first, fall back to simple response
        response_text = generate_llm_response(
            request.message,
            retrieved_docs,
            history,
        )

        # Format sources for response
        sources = [
            {
                "section": doc["metadata"].get("section", "Unknown"),
                "content_preview": doc["content"][:200] + "..." if len(doc["content"]) > 200 else doc["content"],
                "relevance_score": 1.0 - (doc["distance"] or 0) if doc.get("distance") is not None else None
            }
            for doc in retrieved_docs[:3]  # Top 3 sources
        ]
        
        response_payload = ChatResponse(
            response=response_text,
            sources=sources
        )

        if request.conversation_id:
            user_entry = ChatMessage(role="user", content=request.message)
            assistant_entry = ChatMessage(role="assistant", content=response_text)
            append_history(
                request.conversation_id,
                user_entry.model_dump(),
                max_items=request.max_history * 4,
            )
            append_history(
                request.conversation_id,
                assistant_entry.model_dump(),
                max_items=request.max_history * 4,
            )

        return response_payload
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing chat query: {str(e)}"
        )


@app.post("/chat/feedback")
async def chat_feedback(
    message_id: str,
    helpful: bool,
    comment: Optional[str] = None
):
    """
    Collect user feedback on chatbot responses
    """
    # In production, store this in a database
    print(f"Feedback received - Message: {message_id}, Helpful: {helpful}, Comment: {comment}")
    return {"status": "success", "message": "Feedback recorded"}


@app.get("/chat/suggestions")
async def get_suggestions():
    """
    Get suggested questions for users
    """
    return {
        "suggestions": [
            "How do I get started with CoSim?",
            "What simulators are supported?",
            "Can I use GPUs for training?",
            "How does real-time collaboration work?",
            "What's the pricing for CoSim?",
            "Can I run SLAM experiments?",
            "How do I train RL agents?",
            "Is my data secure on CoSim?"
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8006,
        log_level="info"
    )
