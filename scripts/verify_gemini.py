"""Opt-in live provider check using only synthetic notes and a caller-supplied key."""
import os

from planner import ai
from planner.materials import passages


def main():
    if not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("Set GEMINI_API_KEY in your environment first.")
    sources = passages([{
        "id": 1,
        "name": "Synthetic QA notes",
        "pages": [
            "Gradient descent minimizes a differentiable loss by moving parameters in the direction "
            "opposite the gradient. The learning rate controls the size of each step. A very large "
            "learning rate can overshoot a minimum, while a very small rate can slow convergence."
        ],
    }])
    if not ai.extract_topics(sources):
        raise RuntimeError("Gemini returned no valid topics.")
    if not ai.generate_quiz("Gradient descent", sources):
        raise RuntimeError("Gemini returned no valid quiz questions.")
    response = ai.tutor("What controls the size of each step in gradient descent?", sources)
    if not response["citations"]:
        raise RuntimeError("Gemini returned no grounded citation.")
    print("Live Gemini topic extraction, quiz, and cited tutoring passed.")


if __name__ == "__main__":
    main()
