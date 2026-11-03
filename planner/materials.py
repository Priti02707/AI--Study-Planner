"""Local PDF extraction and page-aware lexical retrieval."""
import io
import math
import re
from collections import Counter


def extract_pdf(content):
    from pypdf import PdfReader
    if len(content) > 10 * 1024 * 1024:
        raise ValueError("PDF must be 10 MB or smaller.")
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise ValueError("Upload an unencrypted PDF.")
        if len(reader.pages) > 100:
            raise ValueError("Upload at most 100 pages at a time.")
        pages = []
        for page in reader.pages:
            stream = page.get_contents()
            if stream and len(stream.get_data()) > 5 * 1024 * 1024:
                raise ValueError("A PDF page is too complex. Export a smaller text PDF.")
            pages.append((page.extract_text() or "")[:20000])
        if not any(p.strip() for p in pages):
            raise ValueError("No readable text found. Scanned PDFs need OCR first.")
        return pages
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Could not read this PDF. Try exporting it again.") from exc


def passages(documents):
    result = []
    for doc in documents:
        for page, content in enumerate(doc["pages"], 1):
            for offset in range(0, len(content), 1000):
                chunk = content[offset:offset + 1200].strip()
                if chunk:
                    result.append({"id": f"d{doc['id']}p{page}c{offset}",
                                   "label": f"{doc['name']} · page {page}", "text": chunk})
    return result


def retrieve(query, documents, limit=5):
    """Rank source passages with BM25 and a conservative typo fallback."""
    from difflib import get_close_matches

    chunks = passages(documents)
    tokens = set(re.findall(r"\w{2,}", query.casefold()[:1000])[:20])
    if not tokens or not chunks:
        return []
    counts = [Counter(re.findall(r"\w{2,}", c["text"].casefold())) for c in chunks]
    frequencies = Counter(word for count in counts for word in count)
    average_length = max(1, sum(sum(count.values()) for count in counts) / len(counts))
    matches = {}
    for token in sorted(tokens):
        if token in frequencies:
            matches[token] = 1.0
        elif len(token) >= 5:
            for match in get_close_matches(token, frequencies, n=1, cutoff=0.82):
                matches.setdefault(match, 0.45)
    weights = {
        word: weight * math.log1p((len(chunks) - frequencies[word] + 0.5) / (frequencies[word] + 0.5))
        for word, weight in matches.items()
    }
    scores = []
    for count in counts:
        length_penalty = 1.2 * (0.25 + 0.75 * sum(count.values()) / average_length)
        scores.append(sum(weight * 2.2 * count[word] / (count[word] + length_penalty)
                          for word, weight in weights.items() if count[word]))
    ranked = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
    return [chunks[i] for i in ranked[:limit] if scores[i] > 0]
