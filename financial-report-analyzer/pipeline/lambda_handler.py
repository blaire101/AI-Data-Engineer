"""
pipeline/lambda_handler.py
---------------------------
Triggered by S3 ObjectCreated on the raw bucket.
Runs the full pipeline:
  1. Textract  — extract all text from PDF
  2. OpenSearch — bulk index all sentences
  3. Stage 1   — keyword retrieval per metric (3,000 → 100 candidates)
  4. Stage 2   — SageMaker Keras classifier (100 → Top-3)
  5. Assembly  — merge results → result.json + report.html → S3 analytics
"""

import boto3
import json
import os
from datetime import datetime, timezone
from urllib.parse import unquote_plus

from opensearchpy import OpenSearch, helpers, AWSV4SignerAuth, RequestsHttpConnection

# ── AWS clients ───────────────────────────────────────────────────────────────
textract         = boto3.client("textract")
s3               = boto3.client("s3")
sagemaker_runtime = boto3.client("sagemaker-runtime")

# ── Environment variables ─────────────────────────────────────────────────────
OPENSEARCH_HOST      = os.environ["OPENSEARCH_HOST"]
OPENSEARCH_INDEX     = os.environ.get("OPENSEARCH_INDEX", "annual-reports")
SAGEMAKER_ENDPOINT   = os.environ["SAGEMAKER_ENDPOINT"]
ANALYTICS_BUCKET     = os.environ["ANALYTICS_BUCKET"]
AWS_REGION           = os.environ.get("AWS_REGION", "ap-southeast-1")

# ── Keyword dictionary per financial metric ───────────────────────────────────
METRIC_KEYWORDS = {
    "sales":            ["sales", "revenue", "net sales", "turnover", "increased", "declined"],
    "gross_profit":     ["gross profit", "gross margin", "cost of sales"],
    "ebitda":           ["ebitda", "operating profit", "earnings before"],
    "net_profit":       ["net profit", "net income", "net earnings", "profit after tax"],
    "depreciation":     ["depreciation", "amortization", "amortisation"],
    "interest_expense": ["interest expense", "interest cost", "finance cost"],
    "taxation":         ["tax", "taxation", "income tax", "deferred tax"],
    "total_assets":     ["total assets", "current assets", "non-current assets"],
    "total_debt":       ["total debt", "long-term debt", "borrowings"],
    "working_capital":  ["working capital", "current ratio", "liquidity"],
    "cash_flow":        ["cash flow", "operating cash", "free cash"],
}


def get_opensearch_client():
    credentials = boto3.Session().get_credentials()
    auth = AWSV4SignerAuth(credentials, AWS_REGION)
    return OpenSearch(
        hosts=[{"host": OPENSEARCH_HOST, "port": 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
    )


# ── Step 1: Textract ──────────────────────────────────────────────────────────
def extract_sentences(bucket, key, file_id, company, year):
    response = textract.detect_document_text(
        Document={"S3Object": {"Bucket": bucket, "Name": key}}
    )
    sentences = []
    for i, block in enumerate(response["Blocks"]):
        text = block.get("Text", "").strip()
        if block["BlockType"] == "LINE" and text:
            sentences.append({
                "sentence_id":  i,
                "file_id":      file_id,
                "company":      company,
                "year":         year,
                "page":         block.get("Page", 1),
                "text":         text,
                "word_count":   len(text.split()),
                "extracted_at": datetime.now(timezone.utc).isoformat(),
            })
    print(f"Textract: extracted {len(sentences)} sentences")
    return sentences


# ── Step 2: OpenSearch bulk index ─────────────────────────────────────────────
def index_sentences(client, sentences, file_id):
    actions = [
        {
            "_index":  OPENSEARCH_INDEX,
            "_id":     f"{file_id}_{s['sentence_id']}",
            "_source": s,
        }
        for s in sentences
    ]
    success, errors = helpers.bulk(client, actions, chunk_size=500,
                                   raise_on_error=True)
    print(f"OpenSearch: indexed {success} docs, {len(errors)} errors")


# ── Step 3: Stage 1 — keyword retrieval ──────────────────────────────────────
def keyword_retrieval(client, file_id, metric, top_k=100):
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
    candidates = [
        {
            "text": hit["_source"]["text"],
            "page": hit["_source"]["page"],
        }
        for hit in response["hits"]["hits"]
    ]
    print(f"  Stage 1 [{metric}]: {len(candidates)} candidates")
    return candidates


# ── Step 4: Stage 2 — SageMaker classifier ───────────────────────────────────
def classify_candidates(candidates, metric):
    if not candidates:
        return []

    sentences = [c["text"] for c in candidates]

    response = sagemaker_runtime.invoke_endpoint(
        EndpointName=SAGEMAKER_ENDPOINT,
        ContentType="application/json",
        Body=json.dumps({"sentences": sentences, "metric": metric}),
    )
    results = json.loads(response["Body"].read())

    # Merge page numbers back
    for i, r in enumerate(results):
        r["page"] = candidates[i]["page"]

    # Sort by confidence, return Top-3
    ranked = sorted(results, key=lambda x: x["confidence"], reverse=True)
    top3 = ranked[:3]
    print(f"  Stage 2 [{metric}]: Top-3 scores {[round(r['confidence'],4) for r in top3]}")
    return top3


# ── Step 5: Assembly → report.html ───────────────────────────────────────────
FIELD_LABELS = {
    "E_PL_1":  "Sales",           "E_PL_5":  "Gross Profit",
    "E_PL_38": "Net Profit",      "E_PL_43": "EBITDA",
    "E_PL_11": "Depreciation",    "E_PL_21": "Interest Expense",
    "E_PL_37": "Taxation",        "E_BS_2":  "Total Current Assets",
    "E_BS_61": "Total Current Liabilities", "E_BS_117": "Total Debt",
    "E_BS_115":"Working Capital",  "E_PRO_4": "EBITDA Margin",
}

def fmt(v):
    if isinstance(v, float) and abs(v) < 10:
        return f"{v:.3f}"
    if isinstance(v, (int, float)):
        b = abs(v) / 1e9
        m = abs(v) / 1e6
        return f"${b:.1f}B" if b >= 1 else f"${m:.0f}M"
    return str(v)

def pct(new, old):
    if old and old != 0:
        return round((new - old) / abs(old) * 100, 1)
    return None

def build_report_html(file_id, company, years, fields, metric_top3):
    yr_new, yr_old = years[0], years[1]
    f_new = fields.get(yr_new, {})
    f_old = fields.get(yr_old, {})

    rows = ""
    for code, label in FIELD_LABELS.items():
        v_new = f_new.get(code)
        if v_new is None:
            continue
        v_old = f_old.get(code)
        chg   = pct(v_new, v_old) if v_old else None
        chg_str = f"<span style='color:{'#059669' if chg and chg>0 else '#DC2626'}'>{'+' if chg and chg>0 else ''}{chg}%</span>" if chg else "—"

        evidence = ""
        metric_key = label.lower().replace(" ", "_")
        for ev in metric_top3.get(metric_key, []):
            evidence += f"<blockquote style='margin:4px 0;padding:6px 10px;background:#F8F9FB;border-left:3px solid #A5F3FC;font-size:13px;color:#4B5563;'>p{ev['page']} [{ev['confidence']:.4f}] {ev['sentence']}</blockquote>"

        rows += f"""<tr>
          <td style='padding:10px 12px;font-weight:500;color:#111827;'>{label}</td>
          <td style='padding:10px 12px;text-align:right;'>{fmt(v_new)}</td>
          <td style='padding:10px 12px;text-align:right;'>{fmt(v_old) if v_old else '—'}</td>
          <td style='padding:10px 12px;text-align:right;'>{chg_str}</td>
          <td style='padding:10px 12px;font-size:13px;'>{evidence}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>{company} Financial Analysis</title>
<style>
  body{{font-family:-apple-system,sans-serif;max-width:1100px;margin:40px auto;padding:0 20px;color:#111827;}}
  h1{{font-size:22px;font-weight:700;margin-bottom:4px;}}
  .meta{{font-size:13px;color:#6B7280;margin-bottom:28px;}}
  table{{width:100%;border-collapse:collapse;font-size:14px;}}
  th{{text-align:left;padding:10px 12px;background:#F8F9FB;border-bottom:2px solid #E3E6EE;font-size:12px;letter-spacing:.05em;text-transform:uppercase;color:#6B7280;}}
  tr:nth-child(even){{background:#FAFAFA;}}
  td{{border-bottom:1px solid #F0F0F0;vertical-align:top;}}
  blockquote{{margin:0;}}
</style></head>
<body>
<h1>{company} — Financial Analysis Report</h1>
<div class="meta">Years: {yr_new} vs {yr_old} &nbsp;·&nbsp; Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} &nbsp;·&nbsp; File: {file_id}</div>
<table>
  <thead><tr>
    <th>Metric</th><th style="text-align:right">{yr_new}</th>
    <th style="text-align:right">{yr_old}</th><th style="text-align:right">Change</th>
    <th>Supporting Evidence</th>
  </tr></thead>
  <tbody>{rows}</tbody>
</table>
</body></html>"""
    return html


# ── Main handler ──────────────────────────────────────────────────────────────
def lambda_handler(event, context):
    record     = event["Records"][0]
    raw_bucket = record["s3"]["bucket"]["name"]
    s3_key     = unquote_plus(record["s3"]["object"]["key"])

    # Extract metadata from key: raw/{company}/{year}/{type}/{file_id}.pdf
    parts   = s3_key.split("/")
    company = parts[1] if len(parts) > 1 else "unknown"
    year    = parts[2] if len(parts) > 2 else "unknown"
    file_id = parts[-1].replace(".pdf", "")

    print(f"Starting pipeline for: s3://{raw_bucket}/{s3_key}")

    # Step 1: Textract
    sentences = extract_sentences(raw_bucket, s3_key, file_id, company, year)

    # Step 2: Index into OpenSearch
    client = get_opensearch_client()
    index_sentences(client, sentences, file_id)

    # Step 3 + 4: Per-metric retrieval + classification
    metric_top3 = {}
    for metric in METRIC_KEYWORDS:
        candidates = keyword_retrieval(client, file_id, metric)
        if candidates:
            metric_top3[metric] = classify_candidates(candidates, metric)

    # Step 5: Build report.html
    # fields would normally come from a separate financial data extraction step
    # here we read from event if provided, else use empty dict
    fields = event.get("fields", {})
    years  = event.get("years", [year, str(int(year) - 1)])

    html_content = build_report_html(file_id, company, years, fields, metric_top3)

    # Write report.html to S3 analytics bucket
    html_key = f"reports/{company}/{year}/{file_id}_report.html"
    s3.put_object(
        Bucket=ANALYTICS_BUCKET,
        Key=html_key,
        Body=html_content.encode("utf-8"),
        ContentType="text/html",
    )

    # Write result.json to S3 analytics bucket
    result = {
        "file_id":    file_id,
        "company":    company,
        "years":      years,
        "metrics":    metric_top3,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    json_key = f"reports/{company}/{year}/{file_id}_result.json"
    s3.put_object(
        Bucket=ANALYTICS_BUCKET,
        Key=json_key,
        Body=json.dumps(result, indent=2),
        ContentType="application/json",
    )

    print(f"Pipeline complete. Report: s3://{ANALYTICS_BUCKET}/{html_key}")

    return {
        "statusCode": 200,
        "file_id":    file_id,
        "report_url": f"s3://{ANALYTICS_BUCKET}/{html_key}",
        "sentences":  len(sentences),
    }
