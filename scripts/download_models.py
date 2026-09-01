"""Download the small Chinese RAG models used by the local MVP.

Usage: python scripts/download_models.py [--cache-dir ./models]
"""
import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, default=Path("models"))
    args = parser.parse_args()
    from huggingface_hub import snapshot_download

    models = ["Qwen/Qwen3-Embedding-0.6B", "Qwen/Qwen3-Reranker-0.6B"]
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    for model in models:
        target = snapshot_download(model, cache_dir=str(args.cache_dir), resume_download=True)
        print(f"{model} -> {target}")


if __name__ == "__main__":
    main()
