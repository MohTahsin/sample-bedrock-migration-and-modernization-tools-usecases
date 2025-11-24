# fc_agent_eval.py
"""
Utilities for financial-compliance agent evaluation:
- Chroma DB setup + retriever
- RAG + Web Search tools
- Agent builder (Qwen on Bedrock)
- Prompt formatting & tool / context parsers
"""

import json
import ast
from typing import List, Any, Dict, Optional
from pathlib import Path

from haystack.core.pipeline import Pipeline
from haystack.components.converters import PyPDFToDocument
from haystack.components.preprocessors import DocumentCleaner, DocumentSplitter
from haystack.components.writers import DocumentWriter

from haystack_integrations.document_stores.chroma import ChromaDocumentStore
from haystack_integrations.components.retrievers.chroma import ChromaQueryTextRetriever

from haystack.components.agents import Agent
from haystack.dataclasses import ChatMessage
from haystack.components.builders.chat_prompt_builder import ChatPromptBuilder
from haystack_integrations.components.generators.amazon_bedrock import (
    AmazonBedrockChatGenerator,
)
from haystack.tools import tool

from ddgs import DDGS
from ddgs.exceptions import DDGSException, RatelimitException

from haystack import Document

# -------------------------------------------------------------------
# Global retriever used by rag_tool (call init_chroma_retriever first)
# -------------------------------------------------------------------
_retriever: Optional[ChromaQueryTextRetriever] = None

# Base directory: .../financial-compliance-agent-eval/
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CHROMA_PERSIST_PATH = str(BASE_DIR / "data" / "10k-vec-db")

def init_chroma_retriever(
    pdf_paths: Optional[List[str]] = None,
    persist_path: str = DEFAULT_CHROMA_PERSIST_PATH,
    recreate: bool = False,
    split_length: int = 150,
) -> ChromaQueryTextRetriever:
    """
    Initialize (and optionally rebuild) a ChromaDocumentStore + retriever.

    Args:
        pdf_paths: List of local PDF paths used to (re)build the store.
        persist_path: Local folder where Chroma DB will be persisted.
        recreate: If True, rebuild the store from the provided PDFs.
        split_length: Word-level split length for DocumentSplitter.

    Returns:
        ChromaQueryTextRetriever instance.
    """
    global _retriever

    document_store = ChromaDocumentStore(persist_path=persist_path)

    if recreate and pdf_paths:
        pipe = Pipeline()
        pipe.add_component("converter", PyPDFToDocument())
        pipe.add_component("cleaner", DocumentCleaner())
        pipe.add_component(
            "splitter",
            DocumentSplitter(split_by="word", split_length=split_length),
        )
        pipe.add_component("writer", DocumentWriter(document_store=document_store))

        pipe.connect("converter", "cleaner")
        pipe.connect("cleaner", "splitter")
        pipe.connect("splitter", "writer")

        pipe.run({"converter": {"sources": pdf_paths}})

    _retriever = ChromaQueryTextRetriever(document_store=document_store)
    return _retriever


# -------------------------------------------------------------------
# Tools: web_search + rag_tool (uses global _retriever)
# -------------------------------------------------------------------
@tool
def web_search(keywords: str, region: str = "us-en", max_results: int = 3) -> Any:
    """Search the web for updated information.

    Args:
        keywords: The search query keywords.
        region: The search region: wt-wt, us-en, uk-en, ru-ru, etc.
        max_results: The maximum number of results to return.

    Returns:
        List of dictionaries with search results, or an error string.
    """
    try:
        results = DDGS().text(keywords, region=region, max_results=max_results)
        return results if results else "No results found."
    except RatelimitException:
        return "Rate limit reached. Please try again later."
    except DDGSException as e:
        return f"Search error: {e}"
    except Exception as e:
        return f"Search error: {str(e)}"


@tool
def rag_tool(query: str) -> List[str]:
    """Use this tool to get grounded information for answering queries
    about Amazon (10-K data through 2023).

    Returns a list of text chunks.
    """
    if _retriever is None:
        raise RuntimeError(
            "Chroma retriever is not initialized. "
            "Call init_chroma_retriever(...) before using rag_tool."
        )

    docs = _retriever.run(query=query)["documents"]
    return [doc.content for doc in docs]


# -------------------------------------------------------------------
# Agent builder (Qwen on Bedrock) with your system prompt
# -------------------------------------------------------------------
_SYSTEM_PROMPT = """
You are a professional Amazon research agent with access to two tools:
1. RAG context retrieval tool (`rag_tool`): Contains Amazon 10-K filings data through 2023.
2. Web search tool (`web_search`): For current information beyond 2023.

TOOL SELECTION RULES:
- Use ONLY `rag_tool` for questions about Amazon data from 2023 or earlier.
- Use ONLY `web_search` for questions about Amazon data from 2024 or later.
- NEVER use both tools for a single query.
- You must call the single tool you selected based on the criteria ONCE AND ONLY ONCE.

EXAMPLES FOR RAG TOOL (2023 and earlier data):
- "What was Amazon's revenue in 2022?" → rag_tool
- "Who was Amazon's CFO in 2023?" → rag_tool
- "What were Amazon's operating expenses in 2021?" → rag_tool
- "Who served on Amazon's board of directors in 2023?" → rag_tool

EXAMPLES FOR WEB SEARCH TOOL (2024 and later data):
- "What is Amazon's current stock price?" → web_search
- "What are Amazon's 2024 earnings?" → web_search
- "Who is Amazon's current CEO?" → web_search
- "What new products did Amazon launch in 2024?" → web_search

DECISION LOGIC:
- If the question asks about historical data (2023 or earlier) → rag_tool.
- If the question asks about current/recent data (2024 or later) → web_search.
- If the question doesn't specify a time period but asks for "current" information → web_search.

Give concise, factual answers without preamble. Always use exactly one tool per response.
""".strip()


def build_financial_agent(model_id: str) -> Agent:
    """
    Build and warm up the Haystack Agent using a Bedrock-hosted model.

    Args:
        model_id: Bedrock model ID (e.g., "qwen.qwen3-32b-v1:0").

    Returns:
        Warmed-up haystack Agent instance.
    """
    chat_generator = AmazonBedrockChatGenerator(
        model=model_id,
        generation_kwargs={"temperature": 0.1},
    )

    agent = Agent(
        chat_generator=chat_generator,
        tools=[web_search, rag_tool],
        system_prompt=_SYSTEM_PROMPT,
        exit_conditions=["text"],
        max_agent_steps=2,  # one tool call + one final answer
        raise_on_tool_invocation_failure=False,
    )

    agent.warm_up()
    return agent


# -------------------------------------------------------------------
# Prompt builder (ChatPromptBuilder) – same pattern as your notebook
# -------------------------------------------------------------------
def format_prompt(query: str) -> List[ChatMessage]:
    """
    Build a prompt for the Agent enforcing ONE tool call and time-based
    tool-selection rules via the user message.
    """
    template = [
        ChatMessage.from_user(
            "Using only ONE of the available tools, accurately answer the "
            "following question:\n\n{{question}}\n\n"
            "CRITICAL INSTRUCTIONS:\n"
            "- Select EXACTLY ONE tool based on the time period criteria in your system prompt\n"
            "- Make ONLY ONE tool call - do not break down or modify the query\n"
            "- If the question is about 2023 or earlier Amazon data → use rag_tool\n"
            "- If the question is about 2024+ or current Amazon data → use web_search\n"
            "- Answer directly after your single tool call"
        )
    ]
    builder = ChatPromptBuilder(template=template, required_variables=["question"])
    result = builder.run(question=query)
    return result["prompt"]  # List[ChatMessage]


# -------------------------------------------------------------------
# Tool-context extraction (get_clean_docs) – adapted to rag_tool
# -------------------------------------------------------------------
def _parse_result_payload(payload: Any) -> Any:
    """Return a Python object from payload (str|list|dict)."""
    if isinstance(payload, (list, dict)):
        return payload
    if isinstance(payload, str):
        s = payload.strip()
        # try JSON first
        try:
            return json.loads(s)
        except Exception:
            pass
        # then ast as a fallback
        try:
            return ast.literal_eval(s)
        except Exception:
            # last resort: treat the raw string as a single doc
            return [{"content": s}]
    # Unknown type -> wrap as string
    return [{"content": str(payload)}]


def _coerce_to_documents(obj: Any) -> List[Document]:
    """Normalize various shapes to List[haystack.Document]."""
    # If it's a dict, look for common keys
    if isinstance(obj, dict):
        for key in ("documents", "docs", "results", "retrieved_documents", "retrieved_docs"):
            if key in obj and isinstance(obj[key], list):
                return _coerce_to_documents(obj[key])
        # maybe it’s a single doc-like dict
        obj = [obj]

    # Now expect a list of doc-like items
    docs_out: List[Document] = []
    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, Document):
                docs_out.append(item)
                continue
            if isinstance(item, dict):
                content = (
                    item.get("content")
                    or item.get("text")
                    or item.get("page_content")
                    or ""
                )
                meta = item.get("meta") or item.get("metadata") or {}
                if content is None:
                    content = ""
                docs_out.append(Document(content=content, meta=meta))
                continue
            # anything else -> coerce to string content
            docs_out.append(Document(content=str(item), meta={}))
    return docs_out


def get_clean_docs(answer: Dict[str, Any], target_tool_name: str = "rag_tool") -> List[Document]:
    """
    Walks tool messages in `answer['messages']` and extracts documents
    robustly for the given tool name (defaults to 'rag_tool').
    """
    try:
        # 1) collect candidate payloads from TOOL messages
        candidates = []
        for msg in answer.get("messages", []):
            role = getattr(msg, "_role", None)
            role_val = getattr(role, "value", None) or getattr(msg, "role", None)
            if str(role_val).lower() != "tool":
                continue

            content = getattr(msg, "_content", None) or getattr(msg, "content", None) or []
            if isinstance(content, list):
                for part in content:
                    result = getattr(part, "result", None)
                    origin = getattr(part, "origin", None)
                    tool_name = getattr(origin, "tool_name", None)
                    if result is None:
                        continue
                    if target_tool_name and tool_name == target_tool_name:
                        candidates.append(result)
                    else:
                        # keep a fallback candidate in case no named tool matches
                        candidates.append(result)

        if not candidates:
            return []

        payload = candidates[0]
        parsed = _parse_result_payload(payload)
        return _coerce_to_documents(parsed)

    except Exception as e:
        print(f"Error parsing documents: {e}")
        return []


# -------------------------------------------------------------------
# Tool usage extraction – normalized to 'rag' vs 'web_search'
# -------------------------------------------------------------------
def extract_combined_tools(raw_answer: Dict[str, Any]) -> str:
    """Extract all tools used in one interaction and join with |."""
    tools_used: List[str] = []

    if not raw_answer or "messages" not in raw_answer:
        return "none"

    messages = raw_answer.get("messages", [])

    for message in messages:
        content = getattr(message, "_content", []) or []

        for item in content:
            if hasattr(item, "tool_name"):
                tool_name = item.tool_name

                # Normalize tool names
                if "context_retrieval" in tool_name or "rag_tool" in tool_name:
                    tool_name = "rag"
                elif "web_search" in tool_name:
                    tool_name = "web_search"

                if tool_name not in tools_used:
                    tools_used.append(tool_name)

    return " | ".join(tools_used) if tools_used else "none"
