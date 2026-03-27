"""
Model Drift Detection Module

This module provides utilities for detecting and analyzing drift in LLM outputs,
specifically designed for healthcare Q&A use cases with RAG.

Uses sentence-transformers for embeddings and FAISS for vector search.
"""

from .utils import (
    # Configuration
    DEFAULT_MODEL_ID,
    DEFAULT_REGION,
    DEFAULT_EMBEDDING_MODEL,
    HEALTHCARE_SYSTEM_PROMPT,

    # Data classes
    DriftType,
    ModelResponse,
    RAGResult,
    DriftAnalysis,
    QueryVariation,
    DocumentChunk,

    # Client initialization
    create_bedrock_client,

    # Model invocation
    invoke_bedrock_model,
    invoke_model_with_rag_context,

    # FAISS Vector Store
    FAISSVectorStore,
    initialize_medication_vector_store,
    get_vector_store,

    # RAG retrieval
    retrieve_with_embeddings,
    retrieve_medication_documents_for_query,
    MEDICATION_DOCUMENTS,

    # Metrics computation
    compute_semantic_similarity,
    compute_entity_match_score,
    compute_token_cost_estimate,

    # Drift detection
    detect_verbosity_drift,
    detect_semantic_drift,
    detect_retrieval_drift,
    run_drift_detection_pipeline,
    detect_distribution_drift_ks_test,
    detect_mean_shift,

    # Report generation
    generate_drift_comparison_report,
    generate_batch_drift_summary,

    # Visualization
    print_drift_spectrum_summary,
    print_verbosity_comparison,
    print_semantic_drift_comparison,
    print_drift_results_summary,

    # Test data helpers
    create_metformin_test_variations,
    get_metformin_expected_output,
    get_metformin_expected_entities,
)

__all__ = [
    # Configuration
    "DEFAULT_MODEL_ID",
    "DEFAULT_REGION",
    "DEFAULT_EMBEDDING_MODEL",
    "HEALTHCARE_SYSTEM_PROMPT",

    # Data classes
    "DriftType",
    "ModelResponse",
    "RAGResult",
    "DriftAnalysis",
    "QueryVariation",
    "DocumentChunk",

    # Client initialization
    "create_bedrock_client",

    # Model invocation
    "invoke_bedrock_model",
    "invoke_model_with_rag_context",

    # FAISS Vector Store
    "FAISSVectorStore",
    "initialize_medication_vector_store",
    "get_vector_store",

    # RAG retrieval
    "retrieve_with_embeddings",
    "retrieve_medication_documents_for_query",
    "MEDICATION_DOCUMENTS",

    # Metrics computation
    "compute_semantic_similarity",
    "compute_entity_match_score",
    "compute_token_cost_estimate",

    # Drift detection
    "detect_verbosity_drift",
    "detect_semantic_drift",
    "detect_retrieval_drift",
    "run_drift_detection_pipeline",
    "detect_distribution_drift_ks_test",
    "detect_mean_shift",

    # Report generation
    "generate_drift_comparison_report",
    "generate_batch_drift_summary",

    # Visualization
    "print_drift_spectrum_summary",
    "print_verbosity_comparison",
    "print_semantic_drift_comparison",
    "print_drift_results_summary",

    # Test data helpers
    "create_metformin_test_variations",
    "get_metformin_expected_output",
    "get_metformin_expected_entities",
]
