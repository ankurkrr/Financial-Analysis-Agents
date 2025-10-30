"""
app/tools/qualitative_analysis_tool.py

QualitativeAnalysisTool: a small RAG-style qualitative analyzer for transcripts.
This file keeps heavy ML dependencies lazy and provides a deterministic
fallback embedder so tests and environments without sentence-transformers /
faiss still work.
"""

from typing import List, Dict, Any, Optional
import os

# Lazy default model name
EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")


class _FakeEmbedder:
    """Deterministic lightweight embedder used as a fallback when
    sentence-transformers is not available.

    It produces fixed-size vectors derived from SHA256 of the input text.
    This is sufficient for unit tests and simple retrieval functionality.
    """
    def __init__(self, dim: int = 64):
        import hashlib
        self.dim = int(dim)
        self._hashlib = hashlib

    def encode(self, texts, show_progress_bar: bool = False):
        single = False
        if isinstance(texts, str):
            texts = [texts]
            single = True

        out = []
        for t in texts:
            h = self._hashlib.sha256(t.encode("utf-8")).digest()
            vec = []
            # expand digest bytes into float vector in range [-1, 1]
            for i in range(self.dim):
                b = h[i % len(h)]
                val = (b / 255.0) * 2.0 - 1.0
                vec.append(float(val))
            # normalize to unit norm
            norm = sum(x * x for x in vec) ** 0.5
            if norm > 0:
                vec = [x / norm for x in vec]
            out.append(vec)

        return out[0] if single else out


class QualitativeAnalysisTool:
    """Tool for qualitative analysis of earnings transcripts using RAG pattern.
    
    Ensures robust analysis with:
    1. Fallback to deterministic embeddings if sentence-transformers unavailable
    2. Structured output format for consistent machine readability
    3. Error handling with default values when sections can't be analyzed
    """
    """RAG-based qualitative analysis tool for earnings call transcripts.

    Uses sentence-transformers for embeddings and FAISS for vector search when
    available. If not available, a lightweight deterministic embedder is used
    so the API remains usable in test environments.
    """

    def __init__(self, embed_model_name: str = EMBED_MODEL, embedder: Optional[object] = None):
        self.embedder = embedder
        self.embed_model_name = embed_model_name
        self.index = None
        self.chunks: List[Dict[str, Any]] = []

        # CI / test toggle: if FORCE_FAKE_EMBEDDER is set, use the fake embedder
        try:
            if self.embedder is None and os.getenv("FORCE_FAKE_EMBEDDER", "0").lower() in ("1", "true", "yes"):
                self.embedder = _FakeEmbedder(dim=64)
        except Exception:
            # keep silent on environment-parsing errors; do not break initialization
            pass

    def _chunk_text(self, text: str, chunk_words: int = 300) -> List[str]:
        words = text.split()
        chunks = []
        for i in range(0, len(words), chunk_words):
            chunk = " ".join(words[i:i + chunk_words])
            if chunk.strip():
                chunks.append(chunk)
        return chunks

    def index_transcripts(self, transcripts: List[Dict[str, Any]]) -> bool:
        self.chunks = []
        texts: List[str] = []

        for transcript in transcripts:
            path = transcript.get("local_path")
            if not path:
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except Exception:
                continue

            chunks = self._chunk_text(text, chunk_words=300)
            for i, chunk in enumerate(chunks):
                meta = {
                    "source": transcript.get("name", "unknown"),
                    "chunk_id": f"{transcript.get('name', 'unknown')}_chunk_{i}"
                }
                self.chunks.append({"meta": meta, "text": chunk})
                texts.append(chunk)

        if not texts:
            return False

        # Ensure we have an embedder; try to load sentence-transformers, else fallback
        try:
            if self.embedder is None:
                try:
                    from sentence_transformers import SentenceTransformer
                    self.embedder = SentenceTransformer(self.embed_model_name)
                except Exception:
                    # fallback to deterministic lightweight embedder
                    self.embedder = _FakeEmbedder(dim=64)

            embeddings = self.embedder.encode(texts, show_progress_bar=False)

            # Try to convert embeddings to numpy array for FAISS/indexing
            try:
                import numpy as np
                emb_array = np.array(embeddings)
            except Exception:
                # no numpy; store embeddings as python lists for simple retrieval fallback
                self._embeddings = [list(map(float, e)) for e in embeddings]
                self.index = None
                return True

            if emb_array.ndim == 1:
                emb_array = emb_array.reshape(1, -1)

            # Try to build FAISS index if available
            try:
                import faiss
            except Exception:
                self._embeddings = emb_array.astype('float32')
                self.index = None
                return True

            dimension = emb_array.shape[1]
            self.index = faiss.IndexFlatL2(int(dimension))
            self.index.add(emb_array.astype('float32'))
            return True
        except Exception:
            return False

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if (self.index is None and not hasattr(self, '_embeddings')) or not self.chunks:
            return []

        # ensure embedder is present
        if self.embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self.embedder = SentenceTransformer(self.embed_model_name)
            except Exception:
                self.embedder = _FakeEmbedder(dim=64)

        # If we have a FAISS index, use it
        if self.index is not None:
            try:
                query_embedding = self.embedder.encode([query])
                import numpy as np
                q_arr = np.array(query_embedding).astype('float32')
                distances, indices = self.index.search(q_arr, min(top_k, len(self.chunks)))
            except Exception:
                return []

            results: List[Dict[str, Any]] = []
            for idx, distance in zip(indices[0], distances[0]):
                if idx < len(self.chunks):
                    chunk = self.chunks[idx]
                    results.append({
                        "chunk_id": chunk["meta"]["chunk_id"],
                        "source": chunk["meta"]["source"],
                        "text": chunk["text"][:600],
                        "score": float(distance)
                    })
            return results

        # Otherwise, if we have stored embeddings, do a simple distance-based retrieval
        if hasattr(self, '_embeddings'):
            try:
                import numpy as np
                q_emb = np.array(self.embedder.encode([query])).astype('float32')
                dists = np.linalg.norm(self._embeddings - q_emb, axis=1)
                idxs = np.argsort(dists)[:min(top_k, len(self.chunks))]
                results = []
                for i in idxs:
                    chunk = self.chunks[int(i)]
                    results.append({
                        "chunk_id": chunk["meta"]["chunk_id"],
                        "source": chunk["meta"]["source"],
                        "text": chunk["text"][:600],
                        "score": float(dists[int(i)])
                    })
                return results
            except Exception:
                # numpy not available: pure Python distance computation
                q_emb_raw = self.embedder.encode([query])
                q_emb = q_emb_raw[0] if isinstance(q_emb_raw, list) and len(q_emb_raw) else q_emb_raw
                q_emb = [float(x) for x in q_emb]
                dists = []
                for e in self._embeddings:
                    s = 0.0
                    for a, b in zip(e, q_emb):
                        d = a - b
                        s += d * d
                    dists.append(s ** 0.5)
                idxs = sorted(range(len(dists)), key=lambda i: dists[i])[:min(top_k, len(self.chunks))]
                results = []
                for i in idxs:
                    chunk = self.chunks[int(i)]
                    results.append({
                        "chunk_id": chunk["meta"]["chunk_id"],
                        "source": chunk["meta"]["source"],
                        "text": chunk["text"][:600],
                        "score": float(dists[int(i)])
                    })
                return results

        # last-resort: simple keyword matching
        q = query.lower()
        results = []
        for c in self.chunks:
            if q.split()[0] in c['text'].lower() or any(word in c['text'].lower() for word in q.split(',')):
                results.append({
                    'chunk_id': c['meta']['chunk_id'],
                    'source': c['meta']['source'],
                    'text': c['text'][:600],
                    'score': 0.0
                })
        return results[:top_k]

    def analyze(self, transcripts: List[Dict[str, Any]]) -> Dict[str, Any]:
        success = self.index_transcripts(transcripts)
        if not success:
            return {
                "tool": "QualitativeAnalysisTool",
                "themes": [],
                "management_sentiment": {"score": 0.0, "summary": "insufficient_data"},
                "forward_guidance": [],
                "risks": []
            }

        theme_queries = {
            "demand": "demand, growth, digital transformation, revenue growth, market demand",
            "attrition": "attrition, employee turnover, resignations, hiring, talent, retention",
            "guidance": "guidance, outlook, expect, forecast, projection, next quarter",
            "margins": "margin, profitability, costs, efficiency, operating margin",
            "deals": "deals, pipeline, bookings, wins, contracts, clients"
        }

        themes = []
        for theme_name, query in theme_queries.items():
            results = self.retrieve(query, top_k=5)
            if results:
                themes.append({"theme": theme_name, "count": len(results), "examples": results[:3]})

        positive_queries = ["strong performance", "growth", "optimistic", "positive"]
        negative_queries = ["challenges", "headwinds", "concerns", "pressure"]

        positive_count = 0
        negative_count = 0
        for query in positive_queries:
            positive_count += len(self.retrieve(query, top_k=3))
        for query in negative_queries:
            negative_count += len(self.retrieve(query, top_k=3))

        if positive_count > negative_count:
            sentiment_score = min(0.8, positive_count / max(positive_count + negative_count, 1))
            sentiment_summary = "positive" if sentiment_score > 0.6 else "cautiously optimistic"
        elif negative_count > positive_count:
            sentiment_score = -min(0.8, negative_count / max(positive_count + negative_count, 1))
            sentiment_summary = "negative" if sentiment_score < -0.6 else "cautious"
        else:
            sentiment_score = 0.0
            sentiment_summary = "neutral"

        forward_guidance_results = self.retrieve("guidance, outlook, expect, forecast, next quarter, full year", top_k=5)

        risks = []
        risk_themes = ["attrition", "competition", "macro", "regulation"]
        for theme_name in risk_themes:
            theme_data = next((t for t in themes if t["theme"] == theme_name), None)
            if theme_data and theme_data["count"] > 0:
                risks.append({"name": theme_name, "evidence": [ex["chunk_id"] for ex in theme_data["examples"]]})

        return {
            "tool": "QualitativeAnalysisTool",
            "themes": themes,
            "management_sentiment": {"score": sentiment_score, "summary": sentiment_summary},
            "forward_guidance": forward_guidance_results,
            "risks": risks
        }