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
    chunks = passages(documents)
    tokens = set(re.findall(r"\w{3,}", query.casefold()))
    if not tokens or not chunks:
        return []
    counts = [Counter(re.findall(r"\w{3,}", c["text"].casefold())) for c in chunks]
    frequencies = {word: sum(word in c for c in counts) for word in tokens}
    scores = [sum((1 + math.log(c[word])) * math.log(1 + len(chunks) / (1 + frequencies[word]))
                  for word in tokens if c[word]) / math.sqrt(max(sum(c.values()), 1)) for c in counts]
    ranked = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
    return [chunks[i] for i in ranked[:limit] if scores[i] > 0]
