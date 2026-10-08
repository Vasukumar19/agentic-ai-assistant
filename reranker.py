from sentence_transformers import CrossEncoder

model = None


def _get_model():
    global model
    if model is None:
        model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return model


def rerank(query, items, top_k=5):
    pairs = [
        (query, item["doc"].page_content)
        for item in items
    ]

    scores = _get_model().predict(pairs)

    ranked = sorted(
        zip(items, scores),
        key=lambda x: x[1],
        reverse=True,
    )

    return [item for item, _ in ranked[:top_k]]