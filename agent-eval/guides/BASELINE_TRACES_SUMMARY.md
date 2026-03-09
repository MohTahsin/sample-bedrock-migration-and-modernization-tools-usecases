# Baseline Traces Summary

This document contains all 10 baseline trace JSON files for verification.

---

## 1. good_001_direct_answer.json

**Category**: Clearly Good  
**Description**: Direct answer, no tools needed  
**Expected**: 1 turn, 0 tools, high quality  
**Question**: "What is the capital of France?"  
**Answer**: "The capital of France is Paris."

```json
{
  "resourceSpans": [{
    "resource": {
      "attributes": [
        {"key": "service.name", "value": {"stringValue": "external-agent"}},
        {"key": "deployment.environment", "value": {"stringValue": "test"}}
      ]
    },
    "scopeSpans": [{
      "scope": {"name": "agent-runtime"},
      "spans": [{
        "traceId": "11111111111111111111111111111111",
        "spanId": "aaaaaaaaaaaaaaaa",
        "name": "agent.turn",
        "kind": 1,
        "startTimeUnixNano": "1772832000000000000",
        "endTimeUnixNano": "1772832002500000000",
        "attributes": [
          {"key": "session.id", "value": {"stringValue": "sess-good-001"}},
          {"key": "turn.id", "value": {"stringValue": "turn-1"}}
        ],
        "events": [
          {
            "name": "user.input",
            "timeUnixNano": "1772832000100000000",
            "attributes": [
              {"key": "body.input.messages", "value": {"stringValue": "[{\"role\":\"user\",\"content\":[{\"text\":\"What is the capital of France?\"}]}]"}}
            ]
          },
          {
            "name": "assistant.output",
            "timeUnixNano": "1772832002400000000",
            "attributes": [
              {"key": "body.output.messages", "value": {"stringValue": "[{\"role\":\"assistant\",\"content\":[{\"text\":\"The capital of France is Paris.\"}]}]"}}
            ]
          }
        ]
      }]
    }]
  }]
}
```

---

## 2. good_002_tool_grounded.json

**Category**: Clearly Good  
**Description**: Tool used correctly, answer grounded  
**Expected**: 1 turn, 1 tool, high quality  
**Question**: "What is the weather in Seattle today?"  
**Tool**: weather_api  
**Answer**: "It is 58°F and rainy in Seattle today."

```json
{
  "resourceSpans": [{
    "scopeSpans": [{
      "spans": [{
        "traceId": "22222222222222222222222222222222",
        "spanId": "bbbbbbbbbbbbbbbb",
        "name": "agent.turn",
        "startTimeUnixNano": "1772832100000000000",
        "endTimeUnixNano": "1772832107000000000",
        "attributes": [
          {"key": "session.id", "value": {"stringValue": "sess-good-002"}},
          {"key": "turn.id", "value": {"stringValue": "turn-1"}}
        ],
        "events": [
          {
            "name": "user.input",
            "timeUnixNano": "1772832100100000000",
            "attributes": [
              {"key": "body.input.messages", "value": {"stringValue": "[{\"role\":\"user\",\"content\":[{\"text\":\"What is the weather in Seattle today?\"}]}]"}}
            ]
          },
          {
            "name": "tool.call",
            "timeUnixNano": "1772832101000000000",
            "attributes": [
              {"key": "tool.name", "value": {"stringValue": "weather_api"}},
              {"key": "tool.call.id", "value": {"stringValue": "tool-001"}},
              {"key": "tool.arguments", "value": {"stringValue": "{\"city\":\"Seattle\"}"}}
            ]
          },
          {
            "name": "tool.result",
            "timeUnixNano": "1772832104200000000",
            "attributes": [
              {"key": "tool.call.id", "value": {"stringValue": "tool-001"}},
              {"key": "tool.result", "value": {"stringValue": "{\"temp_f\":58,\"condition\":\"Rain\"}"}}
            ]
          },
          {
            "name": "assistant.output",
            "timeUnixNano": "1772832106800000000",
            "attributes": [
              {"key": "body.output.messages", "value": {"stringValue": "[{\"role\":\"assistant\",\"content\":[{\"text\":\"It is 58°F and rainy in Seattle today.\"}]}]"}}
            ]
          }
        ]
      }]
    }]
  }]
}
```

---

## 3. good_003_two_turn_noise.json

**Category**: Clearly Good  
**Description**: Two-turn conversation with noise  
**Expected**: 2 turns, 1 tool, high quality  
**Turn 1**: "Who wrote Hamlet?" → "William Shakespeare wrote Hamlet."  
**Turn 2**: "When was it first performed?" → "Hamlet was first performed around 1600."

```json
{
  "resourceSpans": [{
    "scopeSpans": [{
      "spans": [
        {
          "traceId": "33333333333333333333333333333333",
          "spanId": "cccccccccccccccc",
          "name": "agent.turn",
          "startTimeUnixNano": "1772832200000000000",
          "endTimeUnixNano": "1772832203000000000",
          "attributes": [
            {"key": "session.id", "value": {"stringValue": "sess-good-003"}},
            {"key": "turn.id", "value": {"stringValue": "turn-1"}}
          ],
          "events": [
            {
              "name": "user.input",
              "timeUnixNano": "1772832200100000000",
              "attributes": [
                {"key": "body.input.messages", "value": {"stringValue": "[{\"role\":\"user\",\"content\":[{\"text\":\"Who wrote Hamlet?\"}]}]"}}
              ]
            },
            {
              "name": "assistant.output",
              "timeUnixNano": "1772832202800000000",
              "attributes": [
                {"key": "body.output.messages", "value": {"stringValue": "[{\"role\":\"assistant\",\"content\":[{\"text\":\"William Shakespeare wrote Hamlet.\"}]}]"}}
              ]
            }
          ]
        },
        {
          "traceId": "33333333333333333333333333333333",
          "spanId": "dddddddddddddddd",
          "name": "agent.turn",
          "startTimeUnixNano": "1772832210000000000",
          "endTimeUnixNano": "1772832217500000000",
          "attributes": [
            {"key": "session.id", "value": {"stringValue": "sess-good-003"}},
            {"key": "turn.id", "value": {"stringValue": "turn-2"}}
          ],
          "events": [
            {
              "name": "user.input",
              "timeUnixNano": "1772832210100000000",
              "attributes": [
                {"key": "body.input.messages", "value": {"stringValue": "[{\"role\":\"user\",\"content\":[{\"text\":\"When was it first performed?\"}]}]"}}
              ]
            },
            {
              "name": "tool.call",
              "timeUnixNano": "1772832211000000000",
              "attributes": [
                {"key": "tool.name", "value": {"stringValue": "search_tool"}},
                {"key": "tool.call.id", "value": {"stringValue": "tool-002"}},
                {"key": "tool.arguments", "value": {"stringValue": "{\"query\":\"Hamlet first performance date\"}"}}
              ]
            },
            {
              "name": "tool.result",
              "timeUnixNano": "1772832214000000000",
              "attributes": [
                {"key": "tool.call.id", "value": {"stringValue": "tool-002"}},
                {"key": "tool.result", "value": {"stringValue": "{\"info\":\"First performed around 1600\"}"}}
              ]
            },
            {
              "name": "assistant.output",
              "timeUnixNano": "1772832217200000000",
              "attributes": [
                {"key": "body.output.messages", "value": {"stringValue": "[{\"role\":\"assistant\",\"content\":[{\"text\":\"Hamlet was first performed around 1600.\"}]}]"}}
              ]
            }
          ]
        }
      ]
    }]
  }]
}
```

---

## 4. bad_001_wrong_math.json

**Category**: Clearly Bad  
**Description**: Clearly wrong answer, no tools  
**Expected**: 1 turn, 0 tools, low quality  
**Question**: "What is 2 + 2?"  
**Answer**: "2 + 2 equals 5." (WRONG)

```json
{
  "resourceSpans": [{
    "scopeSpans": [{
      "spans": [{
        "traceId": "44444444444444444444444444444444",
        "spanId": "eeeeeeeeeeeeeeee",
        "name": "agent.turn",
        "startTimeUnixNano": "1772832300000000000",
        "endTimeUnixNano": "1772832301800000000",
        "attributes": [
          {"key": "session.id", "value": {"stringValue": "sess-bad-001"}},
          {"key": "turn.id", "value": {"stringValue": "turn-1"}}
        ],
        "events": [
          {
            "name": "user.input",
            "timeUnixNano": "1772832300100000000",
            "attributes": [
              {"key": "body.input.messages", "value": {"stringValue": "[{\"role\":\"user\",\"content\":[{\"text\":\"What is 2 + 2?\"}]}]"}}
            ]
          },
          {
            "name": "assistant.output",
            "timeUnixNano": "1772832301600000000",
            "attributes": [
              {"key": "body.output.messages", "value": {"stringValue": "[{\"role\":\"assistant\",\"content\":[{\"text\":\"2 + 2 equals 5.\"}]}]"}}
            ]
          }
        ]
      }]
    }]
  }]
}
```

---

## 5. bad_002_ignores_tool.json

**Category**: Clearly Bad  
**Description**: Tool used but result ignored  
**Expected**: 1 turn, 1 tool, low quality  
**Question**: "What is the weather in Austin?"  
**Tool result**: 84°F, Sunny  
**Answer**: "It is snowing in Austin." (WRONG)

```json
{
  "resourceSpans": [{
    "scopeSpans": [{
      "spans": [{
        "traceId": "55555555555555555555555555555555",
        "spanId": "ffffffffffffffff",
        "name": "agent.turn",
        "startTimeUnixNano": "1772832400000000000",
        "endTimeUnixNano": "1772832408000000000",
        "attributes": [
          {"key": "session.id", "value": {"stringValue": "sess-bad-002"}},
          {"key": "turn.id", "value": {"stringValue": "turn-1"}}
        ],
        "events": [
          {
            "name": "user.input",
            "timeUnixNano": "1772832400100000000",
            "attributes": [
              {"key": "body.input.messages", "value": {"stringValue": "[{\"role\":\"user\",\"content\":[{\"text\":\"What is the weather in Austin?\"}]}]"}}
            ]
          },
          {
            "name": "tool.call",
            "timeUnixNano": "1772832401000000000",
            "attributes": [
              {"key": "tool.name", "value": {"stringValue": "weather_api"}},
              {"key": "tool.call.id", "value": {"stringValue": "tool-003"}},
              {"key": "tool.arguments", "value": {"stringValue": "{\"city\":\"Austin\"}"}}
            ]
          },
          {
            "name": "tool.result",
            "timeUnixNano": "1772832404500000000",
            "attributes": [
              {"key": "tool.call.id", "value": {"stringValue": "tool-003"}},
              {"key": "tool.result", "value": {"stringValue": "{\"temp_f\":84,\"condition\":\"Sunny\"}"}}
            ]
          },
          {
            "name": "assistant.output",
            "timeUnixNano": "1772832407800000000",
            "attributes": [
              {"key": "body.output.messages", "value": {"stringValue": "[{\"role\":\"assistant\",\"content\":[{\"text\":\"It is snowing in Austin.\"}]}]"}}
            ]
          }
        ]
      }]
    }]
  }]
}
```

---

## 6. bad_003_tool_failed_hallucinated.json

**Category**: Clearly Bad  
**Description**: Failed tool and hallucinated confident answer  
**Expected**: 1 turn, 1 tool (failed), low quality  
**Question**: "What is my current account balance?"  
**Tool error**: "upstream timeout"  
**Answer**: "Your current balance is $12,481.22." (HALLUCINATED)

```json
{
  "resourceSpans": [{
    "scopeSpans": [{
      "spans": [{
        "traceId": "66666666666666666666666666666666",
        "spanId": "0000000000000001",
        "name": "agent.turn",
        "startTimeUnixNano": "1772832500000000000",
        "endTimeUnixNano": "1772832506000000000",
        "attributes": [
          {"key": "session.id", "value": {"stringValue": "sess-bad-003"}},
          {"key": "turn.id", "value": {"stringValue": "turn-1"}}
        ],
        "events": [
          {
            "name": "user.input",
            "timeUnixNano": "1772832500100000000",
            "attributes": [
              {"key": "body.input.messages", "value": {"stringValue": "[{\"role\":\"user\",\"content\":[{\"text\":\"What is my current account balance?\"}]}]"}}
            ]
          },
          {
            "name": "tool.call",
            "timeUnixNano": "1772832501000000000",
            "attributes": [
              {"key": "tool.name", "value": {"stringValue": "account_api"}},
              {"key": "tool.call.id", "value": {"stringValue": "tool-004"}},
              {"key": "tool.arguments", "value": {"stringValue": "{\"action\":\"get_balance\"}"}}
            ]
          },
          {
            "name": "tool.result",
            "timeUnixNano": "1772832503500000000",
            "attributes": [
              {"key": "tool.call.id", "value": {"stringValue": "tool-004"}},
              {"key": "tool.error", "value": {"stringValue": "upstream timeout"}},
              {"key": "tool.status", "value": {"stringValue": "error"}}
            ]
          },
          {
            "name": "assistant.output",
            "timeUnixNano": "1772832505800000000",
            "attributes": [
              {"key": "body.output.messages", "value": {"stringValue": "[{\"role\":\"assistant\",\"content\":[{\"text\":\"Your current balance is $12,481.22.\"}]}]"}}
            ]
          }
        ]
      }]
    }]
  }]
}
```

---

## 7. partial_001_incomplete_but_ok.json

**Category**: Partial  
**Description**: Incomplete but acceptable answer  
**Expected**: 1 turn, 0 tools, medium quality  
**Question**: "Explain photosynthesis briefly for a 10-year-old."  
**Answer**: "Plants use sunlight to make food." (Correct but very brief)

```json
{
  "resourceSpans": [{
    "scopeSpans": [{
      "spans": [{
        "traceId": "77777777777777777777777777777777",
        "spanId": "0000000000000002",
        "name": "agent.turn",
        "startTimeUnixNano": "1772832600000000000",
        "endTimeUnixNano": "1772832602000000000",
        "attributes": [
          {"key": "session.id", "value": {"stringValue": "sess-partial-001"}},
          {"key": "turn.id", "value": {"stringValue": "turn-1"}}
        ],
        "events": [
          {
            "name": "user.input",
            "timeUnixNano": "1772832600100000000",
            "attributes": [
              {"key": "body.input.messages", "value": {"stringValue": "[{\"role\":\"user\",\"content\":[{\"text\":\"Explain photosynthesis briefly for a 10-year-old.\"}]}]"}}
            ]
          },
          {
            "name": "assistant.output",
            "timeUnixNano": "1772832601800000000",
            "attributes": [
              {"key": "body.output.messages", "value": {"stringValue": "[{\"role\":\"assistant\",\"content\":[{\"text\":\"Plants use sunlight to make food.\"}]}]"}}
            ]
          }
        ]
      }]
    }]
  }]
}
```

---

## 8. partial_002_hedged_without_tool.json

**Category**: Ambiguous  
**Description**: Answer hedged, tool missing  
**Expected**: 1 turn, 0 tools, low-medium quality  
**Question**: "What time does the downtown library close today?"  
**Answer**: "I think it may close around 5 PM, but you may want to verify." (Should have used a tool)

```json
{
  "resourceSpans": [{
    "scopeSpans": [{
      "spans": [{
        "traceId": "88888888888888888888888888888888",
        "spanId": "0000000000000003",
        "name": "agent.turn",
        "startTimeUnixNano": "1772832700000000000",
        "endTimeUnixNano": "1772832702500000000",
        "attributes": [
          {"key": "session.id", "value": {"stringValue": "sess-partial-002"}},
          {"key": "turn.id", "value": {"stringValue": "turn-1"}}
        ],
        "events": [
          {
            "name": "user.input",
            "timeUnixNano": "1772832700100000000",
            "attributes": [
              {"key": "body.input.messages", "value": {"stringValue": "[{\"role\":\"user\",\"content\":[{\"text\":\"What time does the downtown library close today?\"}]}]"}}
            ]
          },
          {
            "name": "assistant.output",
            "timeUnixNano": "1772832702300000000",
            "attributes": [
              {"key": "body.output.messages", "value": {"stringValue": "[{\"role\":\"assistant\",\"content\":[{\"text\":\"I think it may close around 5 PM, but you may want to verify.\"}]}]"}}
            ]
          }
        ]
      }]
    }]
  }]
}
```

---

## 9. weird_001_duplicate_tool_calls.json

**Category**: Tool Weird  
**Description**: Duplicate tool call events  
**Expected**: 1 turn, 2 raw calls → 1 normalized, medium-high quality  
**Question**: "Search for the population of Canada."  
**Tool**: search_tool (called twice with same ID "dup-1")  
**Answer**: "Canada has about 40 million people."

```json
{
  "resourceSpans": [{
    "scopeSpans": [{
      "spans": [{
        "traceId": "99999999999999999999999999999999",
        "spanId": "1515151515151515",
        "name": "agent.turn",
        "startTimeUnixNano": "1772832800000000000",
        "endTimeUnixNano": "1772832809500000000",
        "attributes": [
          {"key": "session.id", "value": {"stringValue": "sess-weird-001"}},
          {"key": "turn.id", "value": {"stringValue": "turn-1"}}
        ],
        "events": [
          {
            "name": "user.input",
            "timeUnixNano": "1772832800100000000",
            "attributes": [
              {"key": "body.input.messages", "value": {"stringValue": "[{\"role\":\"user\",\"content\":[{\"text\":\"Search for the population of Canada.\"}]}]"}}
            ]
          },
          {
            "name": "tool.call",
            "timeUnixNano": "1772832801000000000",
            "attributes": [
              {"key": "tool.name", "value": {"stringValue": "search_tool"}},
              {"key": "tool.call.id", "value": {"stringValue": "dup-1"}},
              {"key": "tool.arguments", "value": {"stringValue": "{\"query\":\"population of Canada\"}"}}
            ]
          },
          {
            "name": "tool.call",
            "timeUnixNano": "1772832801000000000",
            "attributes": [
              {"key": "tool.name", "value": {"stringValue": "search_tool"}},
              {"key": "tool.call.id", "value": {"stringValue": "dup-1"}},
              {"key": "tool.arguments", "value": {"stringValue": "{\"query\":\"population of Canada\"}"}}
            ]
          },
          {
            "name": "tool.result",
            "timeUnixNano": "1772832805000000000",
            "attributes": [
              {"key": "tool.call.id", "value": {"stringValue": "dup-1"}},
              {"key": "tool.result", "value": {"stringValue": "{\"population\":\"about 40 million\"}"}}
            ]
          },
          {
            "name": "assistant.output",
            "timeUnixNano": "1772832809100000000",
            "attributes": [
              {"key": "body.output.messages", "value": {"stringValue": "[{\"role\":\"assistant\",\"content\":[{\"text\":\"Canada has about 40 million people.\"}]}]"}}
            ]
          }
        ]
      }]
    }]
  }]
}
```

---

## 10. weird_002_orphan_tool_result.json

**Category**: Tool Weird  
**Description**: Orphan tool result, missing linkage  
**Expected**: 1 turn, 0 or 1 inferred tool, medium-low quality  
**Question**: "What is the stock price of XYZ right now?"  
**Tool result appears**: XYZ is trading at 91.32 (no corresponding tool.call event)  
**Answer**: "XYZ is trading at 91.32."

```json
{
  "resourceSpans": [{
    "scopeSpans": [{
      "spans": [{
        "traceId": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "spanId": "2525252525252525",
        "name": "agent.turn",
        "startTimeUnixNano": "1772832900000000000",
        "endTimeUnixNano": "1772832905000000000",
        "attributes": [
          {"key": "session.id", "value": {"stringValue": "sess-weird-002"}},
          {"key": "turn.id", "value": {"stringValue": "turn-1"}}
        ],
        "events": [
          {
            "name": "user.input",
            "timeUnixNano": "1772832900100000000",
            "attributes": [
              {"key": "body.input.messages", "value": {"stringValue": "[{\"role\":\"user\",\"content\":[{\"text\":\"What is the stock price of XYZ right now?\"}]}]"}}
            ]
          },
          {
            "name": "tool.result",
            "timeUnixNano": "1772832902000000000",
            "attributes": [
              {"key": "tool.call.id", "value": {"stringValue": "orphan-1"}},
              {"key": "tool.result", "value": {"stringValue": "{\"symbol\":\"XYZ\",\"price\":91.32}"}}
            ]
          },
          {
            "name": "assistant.output",
            "timeUnixNano": "1772832904800000000",
            "attributes": [
              {"key": "body.output.messages", "value": {"stringValue": "[{\"role\":\"assistant\",\"content\":[{\"text\":\"XYZ is trading at 91.32.\"}]}]"}}
            ]
          }
        ]
      }]
    }]
  }]
}
```

---

## Summary Table

| Trace ID | Category | Turns | Tools | Quality | Key Feature |
|----------|----------|-------|-------|---------|-------------|
| good-001 | clearly_good | 1 | 0 | high | Direct answer |
| good-002 | clearly_good | 1 | 1 | high | Tool grounded |
| good-003 | clearly_good | 2 | 1 | high | Multi-turn |
| bad-001 | clearly_bad | 1 | 0 | low | Wrong answer |
| bad-002 | clearly_bad | 1 | 1 | low | Ignores tool |
| bad-003 | clearly_bad | 1 | 1 (failed) | low | Tool failed + hallucination |
| partial-001 | partial | 1 | 0 | medium | Incomplete but OK |
| partial-002 | ambiguous | 1 | 0 | low-medium | Hedged without tool |
| weird-001 | tool_weird | 1 | 2→1 | medium-high | Duplicate tool calls |
| weird-002 | tool_weird | 1 | 0 or 1 | medium-low | Orphan tool result |

All traces follow the OpenTelemetry trace format with resourceSpans → scopeSpans → spans structure.
