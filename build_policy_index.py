"""Build (or rebuild) the Qdrant policy collection exactly as in task 4.

Same 225 train-split documents (seed 42), same cleaning (banner and repeated template paragraphs removed),
same chunks (600 characters, 100 overlap), same Gemini Embedding 2 vectors (3072, cosine) and payload.
If you already ran task 4 against your Qdrant Cloud cluster you can skip this script: the API reads the
same `sentinel_docs` collection.

Run:  python build_policy_index.py
"""
import hashlib
import json
import os
import re
import unicodedata
import uuid

import pandas as pd
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient, models

import settings
from embeddings import doc_input, embed
from tables import read_table

SEED = 42
SAMPLE_PLAN = {"guidelines": 4, "rba_guides": 1, "regulatory_exercises": 80, "playbooks": 40,
               "investigator_notes": 50, "chargeback_narratives": 50}
CACHE_FILE = os.path.join(settings.OUTPUT_DIR, "embedding_cache.jsonl")
DISCLAIMER = re.compile(r"SYNTHETIC TRAINING MATERIAL\..*?production model output\.\s*", re.S)
PAYLOAD_FIELDS = ["source_document", "document_title", "document_type", "source_body", "topic",
                  "merchant_category", "chunk_number", "chunk_count", "chunk_id", "text"]


def clean_text(text):
    text = unicodedata.normalize("NFKC", str(text))
    text = DISCLAIMER.sub("", text)
    text = re.sub(r"^#\s+.*\n", "", text, count=1)
    text = re.sub(r"^##\s+(.+)$", r"\1:", text, flags=re.M)
    text = re.sub(r"\*\*|`", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def sample_documents():
    docs = read_table(settings.DATA_PATH, "documents")
    docs["source_body"] = "SENTINEL internal"
    docs.loc[docs["title"].str.contains("RBI", na=False), "source_body"] = "RBI"
    docs.loc[docs["title"].str.contains("NPCI", na=False), "source_body"] = "NPCI"
    docs["topic"] = docs["title"].str.extract(r" on (.+)$")[0].fillna("")
    docs["merchant_category"] = docs["template_family"].str.extract(
        r"^(?:investigator_notes|chargeback_narratives|playbooks|regulatory_exercises_[a-z ]+)_([a-z_ ]+?)(?:_\d.*)?$")[0].fillna("")
    train = docs[docs["split"] == "train"].drop_duplicates("content_sha256")
    picked = []
    for kind, n in SAMPLE_PLAN.items():
        pool = train[train["kind"] == kind]
        if kind == "regulatory_exercises":
            part = pool.groupby("topic").sample(4, random_state=SEED)
        elif kind == "playbooks":
            part = pool.groupby("topic").sample(2, random_state=SEED)
        elif kind in ("investigator_notes", "chargeback_narratives"):
            part = pool.groupby("merchant_category").sample(5, random_state=SEED)
        else:
            part = pool.head(n)
        picked.append(part.head(n))
    sample = pd.concat(picked, ignore_index=True)
    sample["clean_text"] = sample["content"].map(clean_text)
    seen, kept = set(), []  # keep each template paragraph once, in the first document that has it
    for text in sample["clean_text"]:
        keep = [p for p in text.split("\n\n") if not (p in seen or seen.add(p))]
        kept.append("\n\n".join(keep))
    sample["clean_text"] = kept
    return sample[sample["clean_text"].str.len() > 50].reset_index(drop=True)


def chunk(sample):
    splitter = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=100,
                                              separators=["\n\n", "\n", ". ", "; ", " "], keep_separator="end")
    rows = []
    for d in sample.itertuples():
        pieces = splitter.split_text(d.clean_text)
        for i, piece in enumerate(pieces):
            rows.append({"chunk_id": f"{d.document_id}::{i}", "source_document": d.document_id,
                         "document_title": d.title, "document_type": d.kind, "source_body": d.source_body,
                         "topic": d.topic, "merchant_category": d.merchant_category,
                         "chunk_number": i, "chunk_count": len(pieces), "text": piece})
    return pd.DataFrame(rows)


def main():
    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
    chunks = chunk(sample_documents())
    print(f"{chunks['source_document'].nunique()} documents, {len(chunks)} chunks")

    def key_of(t):
        return hashlib.sha256(f"{settings.EMBED_MODEL}|{settings.EMBED_DIM}|{t}".encode()).hexdigest()

    cache = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding="utf-8") as f:
            for line in f:
                item = json.loads(line)
                cache[item["key"]] = item["vector"]
    chunks["embed_input"] = [doc_input(t, x) for t, x in zip(chunks["document_title"], chunks["text"])]
    chunks["key"] = chunks["embed_input"].map(key_of)
    todo = chunks[~chunks["key"].isin(cache)]
    print(f"Embedding {len(todo)} chunks with {settings.EMBED_MODEL} via {settings.EMBED_PROVIDER} "
          f"(about {int(todo['embed_input'].str.len().sum() / 4):,} tokens)")
    with open(CACHE_FILE, "a", encoding="utf-8") as f:
        for s in range(0, len(todo), 16):
            b = todo.iloc[s:s + 16]
            for k, v in zip(b["key"], embed(b["embed_input"].tolist())):
                cache[k] = v
                f.write(json.dumps({"key": k, "vector": v}) + "\n")

    client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=60)
    if client.collection_exists(settings.COLLECTION):
        client.delete_collection(settings.COLLECTION)
    client.create_collection(settings.COLLECTION, vectors_config=models.VectorParams(
        size=settings.EMBED_DIM, distance=models.Distance.COSINE))
    for field in ["document_type", "source_body", "source_document", "topic"]:
        client.create_payload_index(settings.COLLECTION, field, models.PayloadSchemaType.KEYWORD)
    client.create_payload_index(settings.COLLECTION, "chunk_number", models.PayloadSchemaType.INTEGER)
    points = [models.PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_URL, r.chunk_id)), vector=cache[r.key],
                                 payload={k: getattr(r, k) for k in PAYLOAD_FIELDS}) for r in chunks.itertuples()]
    for s in range(0, len(points), 64):
        client.upsert(settings.COLLECTION, points=points[s:s + 64], wait=True)
    print("Points stored:", client.count(settings.COLLECTION, exact=True).count)
    chunks.drop(columns=["embed_input", "key"]).to_csv(os.path.join(settings.OUTPUT_DIR, "policy_chunks.csv"), index=False)


if __name__ == "__main__":
    main()
