"""
stage2_classification/model/save_model.py
------------------------------------------
Run this after training your Keras BiLSTM classifier.
Saves model + vocab, packages into model.tar.gz for SageMaker.

Usage:
    python stage2_classification/model/save_model.py
"""

import os
import json
import tarfile
import numpy as np
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Embedding, Bidirectional, LSTM, Dense, Dropout


# ── Replace with your actual trained model + vocab ───────────────────────────

def get_trained_model_and_vocab():
    """
    Plug in your real model and vocab here.
    The structure below matches what inference.py expects:
    - 3 output classes: 0=not_relevant, 1=relevant, 2=highly_relevant
    - input shape: (batch_size, MAX_LEN=64)
    """
    VOCAB_SIZE  = 10000
    EMBED_DIM   = 128
    HIDDEN_DIM  = 128
    MAX_LEN     = 64
    NUM_CLASSES = 3

    model = Sequential([
        Embedding(input_dim=VOCAB_SIZE, output_dim=EMBED_DIM, input_length=MAX_LEN),
        Bidirectional(LSTM(HIDDEN_DIM, return_sequences=False)),
        Dropout(0.3),
        Dense(NUM_CLASSES, activation="softmax"),
    ])
    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy")
    model(np.zeros((1, MAX_LEN), dtype=np.int32))  # initialise weights

    # Replace with your real vocab dict: {"word": index, ...}
    vocab = {"<PAD>": 0, "<UNK>": 1, "sales": 2, "revenue": 3,
             "increased": 4, "profit": 5, "depreciation": 6}

    return model, vocab


# ── Packaging logic ───────────────────────────────────────────────────────────

def save_and_package(model, vocab,
                     output_dir="stage2_classification/model",
                     tarball="stage2_classification/model/model.tar.gz"):
    os.makedirs(output_dir, exist_ok=True)

    model_path = os.path.join(output_dir, "bilstm_model")
    model.save(model_path)
    print(f"Model saved: {model_path}/")

    vocab_path = os.path.join(output_dir, "vocab.json")
    with open(vocab_path, "w", encoding="utf-8") as f:
        json.dump(vocab, f, ensure_ascii=False, indent=2)
    print(f"Vocab saved: {vocab_path}  ({len(vocab)} tokens)")

    with tarfile.open(tarball, "w:gz") as tar:
        tar.add(model_path, arcname="bilstm_model")
        tar.add(vocab_path, arcname="vocab.json")

    print(f"\nPackaged: {tarball}")
    print("Contents:")
    with tarfile.open(tarball, "r:gz") as tar:
        for name in tar.getnames():
            print(f"  {name}")

    return tarball


if __name__ == "__main__":
    model, vocab = get_trained_model_and_vocab()
    save_and_package(model, vocab)
    print("\nNext: run stage2_classification/deploy/upload_and_deploy.py")
