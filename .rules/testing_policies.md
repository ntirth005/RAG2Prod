# Testing & Validation Policies

Standards for test structure, mocking, and continuous evaluation.

## 1. Mocking External Services
* All external LLM or vector embedding APIs MUST be mocked using pytest fixtures during unit testing.
* Use `respx` or `unittest.mock` to intercept network requests.

## 2. Test Execution
* Run sanity tests locally before committing.
* Ensure code coverage on core components (retrieval, ingestion parser) is maintained above 80%.

## 3. Evaluation Judges
* When evaluating prompt changes, use automated LLM judge scripts to check answer relevance and faithfulness on the benchmark suite.
