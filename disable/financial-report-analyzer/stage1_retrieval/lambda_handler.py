"""
stage1_retrieval/lambda_handler.py
-----------------------------------
Stage 1 of the NLP pipeline.
For each financial metric, queries OpenSearch to narrow ~3,000 sentences
down to 100 candidates using BM25 full-text search + TF-IDF re-ranking.

Called by Step Functions after parsing is complete.
Input:  {"file_id": "...", "metric": "sales"}
Output: {"file_id": "...", "metric": "sales", "candidates": [...100 sentences...]}
"""

import boto3
import json
import os
import math
from collections import Counter

from opensearchpy import OpenSearch, AWSV4SignerAuth, RequestsHttpConnection

# ── Keyword dictionary per financial metric ───────────────────────────────────
METRIC_KEYWORDS = {
    "sales":            ["sales", "revenue", "net sales", "turnover", "grew", "increased", "declined"],
    "gross_profit":     ["gross profit", "gross margin", "cost of sales", "cost of goods"],
    "ebitda":           ["ebitda", "operating profit", "earnings before"],
    "net_profit":       ["net profit", "net income", "net earnings", "profit after tax"],
    "depreciation":     ["depreciation", "amortization", "amortisation", "property and equipment"],
    "interest_expense": ["interest expense", "interest cost", "finance cost", "borrowing cost"],
    "taxation":         ["tax", "taxation", "income tax", "deferred tax", "effective tax rate"],
    "total_assets":     ["total assets", "current assets", "non-current assets"],
    "total_debt":       ["total debt", "long-term debt", "borrowings", "liabilities"],
    "working_capital":  ["working capital", "current ratio", "liquidity", "current liabilities"],
    "cash_flow":        ["cash flow", "operating cash", "free cash", "cash and equivalents"],
}

OPENSEARCH_HOST  = os.environ["OPENSEARCH_HOST"]
OPENSEARCH_INDEX = os.environ.get("OPENSEARCH_INDEX", "annual-reports")
TOP_K            = 100


def get_opensearch_client():
    credentials = boto3.Session().get_credentials()
    auth = AWSV4SignerAuth(
        credentials,
        os.environ.get("AWS_REGION", "ap-southeast-1")
    )
    return OpenSearch(
        hosts=[{"host": OPENSEARCH_HOST, "port": 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
    )


def keyword_search(client, file_id, metric, top_k=200):
    """
    BM25 full-text search in OpenSearch.
    Returns up to top_k candidate sentences for this file and metric.
    """
    keywords = METRIC_KEYWORDS.get(metric, [metric])
    query    = " ".join(keywords)

    response = client.search(
        index=OPENSEARCH_INDEX,
        body={
            "query": {
                "bool": {
                    "must": [
                        {"term":  {"file_id": file_id}},
                        {"match": {"text": {"query": query, "operator": "or"}}},
                    ]
                }
            },
            "size": top_k,
        },
    )

    return [
        {
            "sentence_id": hit["_source"]["sentence_id"],
            "text":        hit["_source"]["text"],
            "page":        hit["_source"]["page"],
            "bm25_score":  hit["_score"],
        }
        for hit in response["hits"]["hits"]
    ]


def tfidf_rerank(candidates, metric, top_k=100):
    """
    Re-rank the BM25 candidates using TF-IDF cosine similarity
    against the metric keyword query.
    Returns the top_k most relevant candidates.
    """
    keywords = METRIC_KEYWORDS.get(metric, [metric])

    def tfidf_score(text):
        words     = text.lower().split()
        word_freq = Counter(words)
        score     = 0.0
        for kw in keywords:
            kw_words = kw.lower().split()
            for w in kw_words:
                tf  = word_freq.get(w, 0) / max(len(words), 1)
                idf = math.log(1 + 1 / (1 + word_freq.get(w, 0)))
                score += tf * idf
        return score

    for c in candidates:
        c["tfidf_score"] = tfidf_score(c["text"])

    ranked = sorted(candidates, key=lambda x: x["tfidf_score"], reverse=True)
    return ranked[:top_k]


def lambda_handler(event, context):
    file_id = event["file_id"]
    metric  = event["metric"]

    print(f"Stage 1 — file: {file_id}, metric: {metric}")

    client = get_opensearch_client()

    # Step 1: BM25 keyword search → ~200 candidates
    bm25_results = keyword_search(client, file_id, metric, top_k=200)
    print(f"  BM25 returned {len(bm25_results)} candidates")

    # Step 2: TF-IDF re-rank → top 100
    candidates = tfidf_rerank(bm25_results, metric, top_k=TOP_K)
    print(f"  After TF-IDF re-rank: {len(candidates)} candidates")

    return {
        "file_id":    file_id,
        "metric":     metric,
        "candidates": candidates,
        "count":      len(candidates),
    }
