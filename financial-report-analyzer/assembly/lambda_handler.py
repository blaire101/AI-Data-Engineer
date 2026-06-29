"""
assembly/lambda_handler.py
---------------------------
Final step in the pipeline.
Receives Top-3 sentences for each metric (from Step Functions),
reads the computed financial field values,
and assembles the structured analysis report:
  - output.json  (structured tokens, matching amazon_630.json format)
  - report.md    (human-readable markdown, matching amazon_630.md format)
Both written to the S3 processed bucket.
"""

import boto3
import json
import os
from datetime import datetime, timezone

s3 = boto3.client("s3")
PROCESSED_BUCKET = os.environ["PROCESSED_BUCKET"]

# Field code → human-readable label mapping
FIELD_LABELS = {
    "E_PL_1":   "Sales",
    "E_PL_2":   "Cost of Sales",
    "E_PL_4":   "Transportation Expense",
    "E_PL_5":   "GROSS PROFIT",
    "E_PL_11":  "Depreciation",
    "E_PL_12":  "Amortisation & Noncash Items",
    "E_PL_21":  "Interest expense",
    "E_PL_37":  "Taxation",
    "E_PL_38":  "NET PROFIT",
    "E_PL_43":  "EBITDA",
    "E_BS_2":   "TOTAL CURRENT ASSETS",
    "E_BS_61":  "TOTAL CURRENT LIABILITIES",
    "E_BS_87":  "Current portion of long-term liabilities",
    "E_BS_92":  "Long-Term Debt",
    "E_BS_104": "TOTAL NET WORTH",
    "E_BS_115": "Working Capital",
    "E_BS_117": "Total Debt",
    "E_PRO_4":  "EBITDA Margin",
    "E_COV_8":  "Total Debt/EBITDA",
    "E_LIQ_1":  "Current Ratio",
    "E_BS_4":   "Trade and Other Receivables",
}


def format_value(v):
    if isinstance(v, float) and abs(v) < 10:
        return str(round(v, 3))
    if isinstance(v, (int, float)):
        billions = abs(v) / 1_000_000_000
        millions = abs(v) / 1_000_000
        if billions >= 1:
            return f"${billions:.1f}B"
        elif millions >= 1:
            return f"${millions:.0f}M"
        return str(v)
    return str(v)


def pct_change(new, old):
    if old and old != 0:
        return round((new - old) / abs(old) * 100, 1)
    return None


def assemble_report(fields, metric_top3, company, years):
    """
    fields     : {"2018": {"E_PL_1": 232887000000, ...}, "2017": {...}}
    metric_top3: {"sales": [{"sentence": "...", "page": 31, "probability": 0.9883}, ...], ...}
    company    : "Amazon"
    years      : ["2018", "2017"]
    """
    yr_new, yr_old = years[0], years[1]
    f_new = fields.get(yr_new, {})
    f_old = fields.get(yr_old, {})

    lines = [f"# Financial Analysis Report — {company}\n"]
    lines.append("## Part 1: Executive Summary\n")
    lines.append("### Revenue and Profitability\n")

    for code, label in FIELD_LABELS.items():
        v_new = f_new.get(code)
        v_old = f_old.get(code)
        if v_new is None:
            continue

        pct = pct_change(v_new, v_old) if v_old else None
        direction = "rose" if (pct and pct > 0) else "declined" if (pct and pct < 0) else "was"

        if pct and v_old:
            lines.append(
                f"- **{label}** {direction} by **{abs(pct)}%** to "
                f"**{format_value(v_new)}** in **{yr_new}** "
                f"({yr_old}: **{format_value(v_old)}).\n"
            )
        else:
            lines.append(f"- **{label}**: **{format_value(v_new)}** in **{yr_new}**.\n")

        # Attach supporting sentences if available
        metric_key = label.lower().replace(" ", "_")
        if metric_key in metric_top3:
            for evidence in metric_top3[metric_key]:
                lines.append(
                    f"  > {evidence['sentence']} "
                    f"(p{evidence['page']}, score:{evidence['probability']:.4f})\n"
                )
        lines.append("")

    return "\n".join(lines)


def lambda_handler(event, context):
    """
    event = {
        "file_id":  "...",
        "company":  "Amazon",
        "years":    ["2018", "2017"],
        "fields":   {"2018": {...}, "2017": {...}},
        "results":  {
            "sales":    [{"sentence": "...", "page": 31, "probability": 0.9883}, ...],
            "ebitda":   [...],
            ...
        }
    }
    """
    file_id      = event["file_id"]
    company      = event.get("company", "Unknown")
    years        = event.get("years", ["2018", "2017"])
    fields       = event.get("fields", {})
    metric_top3  = event.get("results", {})

    print(f"Assembling report for {company} {years[0]}")

    # Build markdown report
    md_content = assemble_report(fields, metric_top3, company, years)

    # Write report.md to S3
    md_key = f"reports/{company}/{years[0]}/{file_id}_report.md"
    s3.put_object(
        Bucket=PROCESSED_BUCKET,
        Key=md_key,
        Body=md_content.encode("utf-8"),
        ContentType="text/markdown",
    )

    # Write structured results JSON to S3
    result_obj = {
        "file_id":    file_id,
        "company":    company,
        "years":      years,
        "fields":     fields,
        "top3":       metric_top3,
        "assembled_at": datetime.now(timezone.utc).isoformat(),
    }
    json_key = f"reports/{company}/{years[0]}/{file_id}_result.json"
    s3.put_object(
        Bucket=PROCESSED_BUCKET,
        Key=json_key,
        Body=json.dumps(result_obj, indent=2),
        ContentType="application/json",
    )

    print(f"Report written: s3://{PROCESSED_BUCKET}/{md_key}")
    print(f"JSON written:   s3://{PROCESSED_BUCKET}/{json_key}")

    return {
        "statusCode": 200,
        "file_id":    file_id,
        "report_key": md_key,
        "json_key":   json_key,
    }
