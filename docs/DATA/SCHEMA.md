\# ControlPlane Query Profile Schema



\## Purpose



This document defines the schema for the ControlPlane query dataset.



Each query record should contain the query-profile fields specified in the project data plan.



\## Query Profile Fields



Each query profile should contain the following fields:



| Field | Description |

|---|---|

| `query\_id` | Unique identifier for the query profile. |

| `query` | The query being evaluated. |

| `intent` | The intent represented by the query. |

| `domain` | The domain associated with the query. |

| `knowledge\_type` | The type of knowledge required by the query. |

| `required\_data\_sources` | Data sources required to address the query. |

| `required\_capabilities` | Capabilities required to address the query. |

| `complexity` | Complexity level associated with the query. |

| `risk` | Risk associated with the query. |

| `actionability` | Actionability associated with the query. |

| `sensitivity` | Sensitivity associated with the query. |

| `ambiguity` | Ambiguity associated with the query. |

| `expected\_route` | Expected route for handling the query. |





\## Required Field List



The query profile contains the following fields:



1\. `query\_id`

2\. `query`

3\. `intent`

4\. `domain`

5\. `knowledge\_type`

6\. `required\_data\_sources`

7\. `required\_capabilities`

8\. `complexity`

9\. `risk`

10\. `actionability`

11\. `sensitivity`

12\. `ambiguity`

13\. `expected\_route`



\## Taxonomy Relationship



The query dataset uses the initial taxonomy defined in the project data plan.



Queries may have multiple labels.


## Initial Taxonomy

The initial taxonomy consists of the following labels:

- `PUBLIC_FACTUAL`
- `PRIVATE_FACTUAL`
- `RAG`
- `INSUFFICIENT_RAG`
- `SQL`
- `ANALYTICAL`
- `REASONING`
- `CODING`
- `RECOMMENDATION`
- `DECISION_SUPPORT`
- `MEMORY`
- `CHAT_HISTORY`
- `AGENTIC`
- `HIGH_RISK_AGENTIC`
- `SENSITIVE`
- `AMBIGUOUS`
- `MULTI_SOURCE`
- `MULTI_STEP`

These taxonomy labels are not mutually exclusive. A single query may be assigned multiple labels.


\## Currently Unspecified



The project data plan specifies the query-profile fields but does not specify formal datatypes, validation rules, or complete allowed-value sets for every field.



These details should not be invented during the initial schema definition and require clarification or later specification where necessary.

