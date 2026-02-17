# Requirements Document

## Introduction

This document specifies the requirements for implementing a Generic JSON adapter and normalized schema for the agent-eval module. This is phase 1 of a larger evaluation system that will enable offline analysis of agent execution traces. The system must convert arbitrary trace formats into a standardized schema, handle missing data gracefully, and provide utilities for extracting logs from CloudWatch while maintaining strict isolation within the agent-eval module.

## Glossary

- **Normalized_Schema**: A standardized JSON schema that represents agent execution traces in a consistent format across different source systems
- **Generic_JSON_Adapter**: A Python module that transforms input trace files conforming to a generic JSON structure into the normalized schema format
- **Trace_File**: A JSON file containing recorded execution data from an agent run, including steps, timing, and outcomes
- **CloudWatch_Log_Extractor**: A utility tool that fetches logs from AWS CloudWatch and transforms them into Generic JSON trace files
- **Agent_Eval_Module**: The isolated evaluation framework located under the agent-eval/ directory
- **Run_ID**: A unique identifier for a single agent execution trace
- **Step**: An individual action or operation within an agent execution, such as tool invocation or reasoning
- **Latency**: The time duration in milliseconds for completing an operation

## Requirements

### Requirement 1: Normalized Schema Definition

**User Story:** As a developer, I want a standardized schema for agent traces, so that I can consistently analyze execution data from different sources.

#### Acceptance Criteria

1. THE Normalized_Schema SHALL be defined as a JSON Schema file located at agent_eval/schemas/normalized_run.schema.json
2. THE Normalized_Schema SHALL include a run_id field of type string at the run level
3. THE Normalized_Schema SHALL include a metadata field of type object for run-level metadata
4. THE Normalized_Schema SHALL include an adapter_stats field of type object for adapter processing statistics
5. THE Normalized_Schema SHALL include a turns field of type array containing turn objects for multi-turn conversations
6. WHEN a turn object is defined, THE Normalized_Schema SHALL require fields: turn_id (string), user_query (string), final_answer (string), steps (array), total_latency_ms (number or null), and confidence (number between 0 and 1)
7. THE turn object MAY include optional fields: request_id (string), timestamp (string in ISO 8601 format)
8. WHEN a step object is defined, THE Normalized_Schema SHALL support fields: type (string), kind (string), name (string), status (string), start_ts (string or null), end_ts (string or null), latency_ms (number or null), span_id (string or null), parent_span_id (string or null), tool_run_id (string or null), attributes (object), and raw (object)
9. THE Normalized_Schema SHALL include normalized_latency_ms (number or null) derived from trusted timestamps for each turn
10. THE Normalized_Schema SHALL include runtime_reported_latency_ms (number or null) if provided by the source system for each turn
11. WHEN timestamps are missing or invalid, THE Normalized_Schema SHALL allow latency_ms to be null
12. THE Normalized_Schema SHALL be valid according to JSON Schema Draft 7 or later specifications

### Requirement 2: Generic JSON Adapter Implementation

**User Story:** As a developer, I want to convert generic JSON trace files into the normalized format, so that I can process traces from various sources uniformly.

#### Acceptance Criteria

1. THE Generic_JSON_Adapter SHALL be implemented as a Python module at agent_eval/adapters/generic_json/adapter.py (or agent_eval/adapters/generic_json.py)
2. THE Generic_JSON_Adapter SHALL have an associated configuration file at agent_eval/adapters/generic_json/adapter_config.yaml
3. THE adapter_config.yaml SHALL define field mapping rules and step classification rules in a config-driven manner
4. WHEN the Generic_JSON_Adapter receives a valid Generic JSON trace file, THE Generic_JSON_Adapter SHALL transform it into the Normalized_Schema format
5. WHEN the Generic_JSON_Adapter encounters a trace file with missing optional fields, THE Generic_JSON_Adapter SHALL emit null values with a confidence penalty if the schema allows nullable fields
6. WHEN the Generic_JSON_Adapter encounters a trace file with missing required-by-schema fields, THE Generic_JSON_Adapter SHALL emit null with confidence_penalty for most fields, but raise a validation error only if no events exist or input is unreadable
7. THE Generic_JSON_Adapter SHALL validate output against the Normalized_Schema before returning results
8. THE Generic_JSON_Adapter SHALL NOT assume the existence of optional attributes without explicit checks
9. THE Generic_JSON_Adapter SHALL calculate normalized_latency_ms from trusted timestamps when available
10. THE Generic_JSON_Adapter SHALL preserve runtime_reported_latency_ms if provided by the source system
11. WHEN timestamps are missing or invalid, THE Generic_JSON_Adapter SHALL set latency_ms to null, emit a warning, and apply a confidence penalty
12. THE Generic_JSON_Adapter SHALL support multi-turn traces with stitched conversations

### Requirement 3: Graceful Error Handling

**User Story:** As a developer, I want the adapter to handle malformed or incomplete data gracefully, so that partial traces can still be processed without crashing the system.

#### Acceptance Criteria

1. WHEN the Generic_JSON_Adapter encounters a JSON parsing error, THE Generic_JSON_Adapter SHALL raise a descriptive error indicating the file path and parsing issue
2. WHEN the Generic_JSON_Adapter encounters missing required fields, THE Generic_JSON_Adapter SHALL raise a validation error listing all missing fields
3. WHEN the Generic_JSON_Adapter encounters invalid field types, THE Generic_JSON_Adapter SHALL raise a type error with the field name and expected type
4. WHEN the Generic_JSON_Adapter encounters an empty steps array, THE Generic_JSON_Adapter SHALL accept it as valid and set total_latency_ms to zero
5. THE Generic_JSON_Adapter SHALL log warnings for missing optional fields without failing the transformation

### Requirement 4: CloudWatch Log Extraction Utility

**User Story:** As a developer, I want to extract CloudWatch logs with configurable time ranges and convert them to normalized format, so that I can analyze historical agent executions.

#### Acceptance Criteria

1. THE CloudWatch_Log_Extractor SHALL be implemented as a Python module at agent_eval/tools/cloudwatch_extractor.py
2. WHEN invoked, THE CloudWatch_Log_Extractor SHALL fetch logs from AWS CloudWatch for a configurable time range (default: 90 days)
3. THE CloudWatch_Log_Extractor SHALL support configuration of time range via command-line arguments or configuration file
4. THE CloudWatch_Log_Extractor SHALL support running without knowing the exact log group name by allowing discovery via prefix/regex pattern matching
5. WHEN log group name is not provided and cannot be discovered, THE CloudWatch_Log_Extractor SHALL emit an explicit failure message
6. WHEN the CloudWatch_Log_Extractor retrieves logs, THE CloudWatch_Log_Extractor SHALL parse them into Generic JSON structure and pass to the Generic_JSON_Adapter for transformation
7. THE CloudWatch_Log_Extractor SHALL save normalized traces as individual JSON files with unique filenames based on run_id
8. WHEN AWS credentials are missing or invalid, THE CloudWatch_Log_Extractor SHALL raise an authentication error with guidance
9. THE CloudWatch_Log_Extractor SHALL support configuration of log group name and query filters via command-line arguments or configuration file
10. WHEN no logs are found for the specified time range, THE CloudWatch_Log_Extractor SHALL return an empty result set without error

### Requirement 5: Adapter Independence from CloudWatch

**User Story:** As a developer, I want the Generic JSON adapter to be independent of CloudWatch APIs, so that it can process traces from any source without cloud-specific dependencies.

#### Acceptance Criteria

1. THE Generic_JSON_Adapter SHALL NOT import or depend on boto3 or any AWS SDK libraries
2. THE Generic_JSON_Adapter SHALL NOT import or depend on CloudWatch-specific modules
3. THE Generic_JSON_Adapter SHALL only consume JSON files conforming to the Generic JSON format
4. THE CloudWatch_Log_Extractor SHALL be the only module that interacts with AWS CloudWatch APIs
5. WHEN the Generic_JSON_Adapter is tested, THE Generic_JSON_Adapter SHALL function correctly without AWS credentials or network access

### Requirement 6: Schema Validation and Compliance

**User Story:** As a developer, I want to validate traces against the normalized schema, so that I can ensure data quality and catch format errors early.

#### Acceptance Criteria

1. THE Generic_JSON_Adapter SHALL validate all output against the Normalized_Schema using a JSON Schema validator
2. WHEN validation fails, THE Generic_JSON_Adapter SHALL raise an error with details about which fields failed validation
3. THE Generic_JSON_Adapter SHALL support validation of historical traces for regression testing
4. WHEN processing multiple trace files, THE Generic_JSON_Adapter SHALL report validation status for each file individually
5. THE Generic_JSON_Adapter SHALL provide a validation summary indicating total files processed, successful validations, and failures

### Requirement 7: Module Isolation and Workspace Structure

**User Story:** As a developer, I want all development isolated within the agent-eval module, so that I don't introduce breaking changes to other parts of the repository.

#### Acceptance Criteria

1. THE Agent_Eval_Module SHALL contain all new code under the agent-eval/ directory
2. THE Agent_Eval_Module SHALL NOT modify root-level requirements.txt or pyproject.toml files
3. THE Agent_Eval_Module SHALL NOT modify shared utilities outside the agent-eval/ directory
4. THE Agent_Eval_Module SHALL NOT modify CI configuration files outside the agent-eval/ directory
5. THE Agent_Eval_Module SHALL declare all dependencies in agent-eval/pyproject.toml
6. THE Agent_Eval_Module SHALL NOT introduce dependencies on non agent-eval modules; MAY reuse utility code via copying or internal module import within agent-eval/
7. THE Agent_Eval_Module SHALL follow the directory structure: schemas/, adapters/, tools/, utils/

### Requirement 8: Edge Case Handling

**User Story:** As a developer, I want the system to handle edge cases robustly, so that unusual or malformed data doesn't cause system failures.

#### Acceptance Criteria

1. WHEN a trace file contains steps with negative latency values, THE Generic_JSON_Adapter SHALL treat them as zero and log a warning
2. WHEN a trace file contains duplicate run_id values, THE Generic_JSON_Adapter SHALL process each independently without conflict
3. WHEN a trace file contains extremely large step arrays (>10,000 steps), THE Generic_JSON_Adapter SHALL process them without memory errors
4. WHEN a trace file contains Unicode characters in string fields, THE Generic_JSON_Adapter SHALL preserve them correctly
5. WHEN a trace file contains null values for optional fields, THE Generic_JSON_Adapter SHALL replace them with appropriate defaults
6. WHEN timestamp format is invalid, THE Generic_JSON_Adapter SHALL mark ts_trusted as false, keep event ordered by source_index, reduce confidence, and only fail if no usable ordering exists and no anchors are available
7. WHEN a trace file contains orphan tool results (tool results without corresponding tool calls), THE Generic_JSON_Adapter SHALL handle them gracefully with appropriate confidence penalties
8. WHEN a trace file contains tool-looking text without actual TOOL_CALL markers, THE Generic_JSON_Adapter SHALL not misclassify them as tool invocations

### Requirement 9: Testing and Validation Against Historical Data

**User Story:** As a developer, I want to test the adapter against historical traces, so that I can ensure it handles real-world data correctly.

#### Acceptance Criteria

1. THE Generic_JSON_Adapter SHALL be tested against a set of historical trace files representing diverse scenarios
2. WHEN tested against historical traces with clean valid inputs, THE Generic_JSON_Adapter SHALL achieve 100% schema compliance
3. WHEN tested against messy real traces, THE Generic_JSON_Adapter SHALL produce output with adapter_stats and non-zero confidence penalties instead of failing (except for malformed JSON or no events)
4. WHEN tested against historical traces with missing fields, THE Generic_JSON_Adapter SHALL handle them according to the graceful error handling requirements
5. THE Generic_JSON_Adapter SHALL be tested with traces containing minimum required fields only
6. THE Generic_JSON_Adapter SHALL be tested with traces containing all optional fields populated
7. THE Generic_JSON_Adapter SHALL be tested with traces containing edge cases such as empty steps arrays and zero latencies
8. THE Generic_JSON_Adapter SHALL be tested with stitched multi-turn traces
9. THE Generic_JSON_Adapter SHALL be tested with orphan tool results (tool results without corresponding tool calls)
10. THE Generic_JSON_Adapter SHALL be tested with tool-looking text without actual TOOL_CALL markers
