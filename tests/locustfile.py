import os
from locust import HttpUser, task, between

# We can run locust like this: locust -f tests/locustfile.py --host=http://localhost:8000
class RAG2ProdUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def check_health(self):
        """Simulate frequent liveness checks from load balancers"""
        self.client.get("/health/liveness", name="/health/liveness")

    @task(1)
    def check_readiness(self):
        """Simulate readiness checks (hits DB)"""
        self.client.get("/health/readiness", name="/health/readiness")

    @task(2)
    def search_query(self):
        """Simulate hybrid retrieval search"""
        payload = {
            "query_text": "What are the security policies?",
            "top_k": 5,
            "score_threshold": 0.5
        }
        self.client.post("/api/v1/retrieval/search", json=payload, name="/api/v1/retrieval/search")

    @task(1)
    def full_rag_query(self):
        """Simulate a full RAG streaming generation request"""
        payload = {
            "query_text": "Summarize the latest deployment architecture",
            "top_k": 3,
            "stream": True,
            "provider": "deepseek"
        }
        # For streams, we just want to ensure it connects and returns 200 chunked
        with self.client.post("/api/v1/query/stream", json=payload, stream=True, name="/api/v1/query/stream", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")
