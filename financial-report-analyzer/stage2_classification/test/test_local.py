"""
stage2_classification/test/test_local.py
-----------------------------------------
Test the model locally before deploying to SageMaker.
No AWS account needed.

Usage:
    python stage2_classification/test/test_local.py
"""

import sys, json, os
import numpy as np

sys.path.insert(0, ".")

# Reuse inference.py functions directly
from stage2_classification.inference import model_fn, input_fn, predict_fn

TEST_SENTENCES = [
    "Sales increased 31% in 2017 and 2018, compared to the comparable prior years.",
    "North America sales increased 33% in 2017 and 2018.",
    "International sales increased 23% and 21% in 2017, and 2018.",
    "AWS sales increased 43% and 47% in 2017 and 2018.",
    "The company faces significant regulatory challenges.",
    "Changes in foreign currency exchange rates impacted net sales by $(550) million.",
    "Interest expense was $484 million, $848 million, and $1.4 billion in 2016, 2017, and 2018.",
]

MODEL_DIR = "stage2_classification/model"

print("=" * 60)
print("Local test — no AWS needed")
print("=" * 60)

print("\n[1/3] Loading model ...")
model_dict = model_fn(MODEL_DIR)

print("\n[2/3] Preparing input ...")
sentences = input_fn(json.dumps({"sentences": TEST_SENTENCES}))

print("\n[3/3] Running inference ...")
results = predict_fn(sentences, model_dict)
ranked  = sorted(results, key=lambda x: x["confidence"], reverse=True)

print("\nResults (ranked by confidence):")
print("-" * 60)
for i, r in enumerate(ranked, 1):
    bar   = "█" * int(r["confidence"] * 20)
    print(f"  {i}. [{r['confidence']:.4f}] {r['text'][:65]}...")
    print(f"         {bar}")

print(f"\nTop-3:")
for i, r in enumerate(ranked[:3], 1):
    print(f"  {i}. [score:{r['confidence']:.4f}] {r['text'][:65]}...")

print("\nLocal test passed. Proceed to deploy.")
