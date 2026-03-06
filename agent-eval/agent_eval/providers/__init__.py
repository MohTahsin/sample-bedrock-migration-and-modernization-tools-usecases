"""
Provider implementations for judge clients.

This module contains concrete implementations of JudgeClient for
various LLM providers (Bedrock, OpenAI, Anthropic, etc.).
"""

from agent_eval.providers.bedrock_client import BedrockJudgeClient

__all__ = ['BedrockJudgeClient']
