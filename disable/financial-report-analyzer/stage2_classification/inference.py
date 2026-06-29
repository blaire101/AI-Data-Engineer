"""
stage2_classification/inference.py
------------------------------------
SageMaker calls these four functions automatically when the endpoint
receives a request from the Stage 2 Lambda.

Do NOT call these functions yourself — SageMaker manages the lifecycle.
"""

import os
import json
import numpy as np
import tensorflow as tf

MAX_LEN = 64   # must match training


def model_fn(model_dir):
    """Called once on endpoint startup — loads model + vocab."""
    model = tf.keras.models.load_model(
        os.path.join(model_dir, "bilstm_model")
    )
    with open(os.path.join(model_dir, "vocab.json")) as f:
        vocab = json.load(f)
    print(f"BiLSTM loaded. Input shape: {model.input_shape}")
    return {"model": model, "vocab": vocab}


def input_fn(request_body, content_type="application/json"):
    """Parse JSON sent by Lambda: {"sentences": [...]}"""
    data = json.loads(request_body)
    if "sentences" not in data or not data["sentences"]:
        raise ValueError("Request must contain non-empty 'sentences' list.")
    return data["sentences"]


def predict_fn(sentences, model_dict):
    """Tokenize → pad → BiLSTM → return confidence scores."""
    model = model_dict["model"]
    vocab = model_dict["vocab"]
    UNK   = vocab.get("<UNK>", 0)

    batch = []
    for sentence in sentences:
        tokens = sentence.lower().split()
        ids    = [vocab.get(t, UNK) for t in tokens]
        ids    = ids[:MAX_LEN] + [0] * (MAX_LEN - len(ids))
        batch.append(ids)

    probs = model.predict(np.array(batch, dtype=np.int32), verbose=0)

    return [
        {
            "text":       sentence,
            "confidence": float(probs[i][2]),  # index 2 = highly_relevant
            "all_probs":  probs[i].tolist(),
        }
        for i, sentence in enumerate(sentences)
    ]


def output_fn(prediction, accept="application/json"):
    return json.dumps(prediction), accept
