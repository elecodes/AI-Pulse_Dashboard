"""Heuristic keyword-based classifier — works out of the box with no API keys.

Scans article title and summary for domain-specific keywords and assigns a
category label.  Uses the article's existing summary (truncated) when no LLM
provider is configured.

Categories and keywords are defined in ``KEYWORD_RULES`` — ordered by priority
(first match wins).
"""

from __future__ import annotations

import logging
import re
from typing import Pattern

from backend.classifier.base import AbstractClassifier, ClassificationError
from backend.models.article import Article

logger = logging.getLogger(__name__)

# Category rule: (regex pattern, category_name)
# Ordered by specificity — more specific patterns first.
_KEYWORD_RULES: list[tuple[Pattern[str], str]] = [
    (re.compile(r"\b(llm|large language model|foundation model)\b", re.IGNORECASE), "LLM"),
    (re.compile(r"\b(gpt|chatgpt|openai|o1|o3)\b", re.IGNORECASE), "LLM"),
    (re.compile(r"\b(claude|anthropic)\b", re.IGNORECASE), "LLM"),
    (re.compile(r"\b(bert|gpt-4|gpt-5|mistral|llama|phi|gemma|deepseek)\b", re.IGNORECASE), "LLM"),
    (re.compile(r"\b(transformer|attention mechanism|self-attention)\b", re.IGNORECASE), "LLM"),
    (re.compile(r"\b(tokens?|tokenization|tokenizer)\b", re.IGNORECASE), "LLM"),
    (re.compile(r"\b(computer vision|image recognition|object detection)\b", re.IGNORECASE), "Computer Vision"),
    (re.compile(r"\b(cnn|convolutional|resnet|yolo|vit|vision transformer)\b", re.IGNORECASE), "Computer Vision"),
    (re.compile(r"\b(segmentation|image generation|stable diffusion|dall-e)\b", re.IGNORECASE), "Computer Vision"),
    (re.compile(r"\b(diffusion|vae|gan|generative adversarial)\b", re.IGNORECASE), "Generative AI"),
    (re.compile(r"\b(nlp|natural language|text classification|ner|named entity)\b", re.IGNORECASE), "NLP"),
    (re.compile(r"\b(sentiment|machine translation|text generation|summarization)\b", re.IGNORECASE), "NLP"),
    (re.compile(r"\b(safety|alignment|ai safety|ethical|bias|fairness)\b", re.IGNORECASE), "AI Safety"),
    (re.compile(r"\b(reinforcement|rl|reward|deep q|policy gradient|ppo)\b", re.IGNORECASE), "Reinforcement Learning"),
    (re.compile(r"\b(robot|robotics|autonomous|drone|manipulation)\b", re.IGNORECASE), "Robotics"),
    (re.compile(r"\b(speech|whisper|voice|tts|asr|audio|text-to-speech)\b", re.IGNORECASE), "Audio/Speech"),
    (re.compile(r"\b(machine learning|deep learning|neural network)\b", re.IGNORECASE), "Machine Learning"),
    (re.compile(r"\b(retrieval augmented|rag|embeddings|vector database)\b", re.IGNORECASE), "RAG / Search"),
    (re.compile(r"\b(agent|multi-agent|tool use|function calling)\b", re.IGNORECASE), "Agents"),
    (re.compile(r"\b(mixture of experts|moe|sparse|distillation|quantization)\b", re.IGNORECASE), "Efficiency"),
    (re.compile(r"\b(fine.?tun(e|ing)|lora|qlora|adapter|peft)\b", re.IGNORECASE), "Fine-tuning"),
    (re.compile(r"\b(data(?:set|base)?|analytics|benchmark|evaluation)\b", re.IGNORECASE), "Data & Evaluation"),
    # HuggingFace model IDs — image-related keywords
    (re.compile(r"\b(image|edit|inpaint|outpaint|sdxl|pixart|vae)\b", re.IGNORECASE), "Computer Vision"),
    (re.compile(r"\b(diffusers?|playground|krea|ideogram)\b", re.IGNORECASE), "Computer Vision"),
    (re.compile(r"\b(vision|visual)\b", re.IGNORECASE), "Computer Vision"),
    (re.compile(r"\b(comfy|bernini|flux|upscaler)\b", re.IGNORECASE), "Computer Vision"),
    (re.compile(r"\b(cosmos|ltx|wan|sam)\b", re.IGNORECASE), "Computer Vision"),
    # HuggingFace model IDs — quantization / optimization
    (re.compile(r"\b(gguf|awq|gptq|exl2?)\b", re.IGNORECASE), "Efficiency"),
    # Multi-agent / swarm patterns
    (re.compile(r"\b(swarm|crew)\b", re.IGNORECASE), "Agents"),
    # Data / preprocessing
    (re.compile(r"\b(pipeline|dataset|preprocess)\b", re.IGNORECASE), "Data & Evaluation"),
    # LLM model IDs — additional org/model names
    (re.compile(r"\b(qwen|glm|chatglm|grok)\b", re.IGNORECASE), "LLM"),
    (re.compile(r"\b(granite|olmo|dolphin|zyphra|sakura)\b", re.IGNORECASE), "LLM"),
    (re.compile(r"\b(mistral|ministral|mixtral)\b", re.IGNORECASE), "LLM"),
    # NLP model IDs
    (re.compile(r"\b(translate|nllb)\b", re.IGNORECASE), "NLP"),
    # Audio model IDs
    (re.compile(r"\b(speaker|diarization|piper|voice)\b", re.IGNORECASE), "Audio/Speech"),
    # Model fine-tuning / adapter prefixes
    (re.compile(r"\b(abliterated|uncensored)\b", re.IGNORECASE), "Fine-tuning"),
    # Loose substring patterns for model IDs (no trailing \b)
    # Compound names like "krea2" won't match \bkrea\b
    (re.compile(r"krea|comfy|bernini|ideogram", re.IGNORECASE), "Computer Vision"),
    (re.compile(r"ltx|wan|flux", re.IGNORECASE), "Computer Vision"),
    (re.compile(r"cosmos|pixart|diffuser", re.IGNORECASE), "Computer Vision"),
    (re.compile(r"qwen|mistral|ministral|mixtral|granite|olmo|dolphin|grok|zyphra|sakura", re.IGNORECASE), "LLM"),
    # Loose arXiv title patterns — catch academic phrasing missed by \b
    (re.compile(r"agent", re.IGNORECASE), "Agents"),
    (re.compile(r"llm", re.IGNORECASE), "LLM"),
    (re.compile(r"attention", re.IGNORECASE), "LLM"),
    (re.compile(r"reinforcement", re.IGNORECASE), "Reinforcement Learning"),
    (re.compile(r"continual|incremental|lifelong", re.IGNORECASE), "Machine Learning"),
    (re.compile(r"pose|tracking|slam|segmentation|detection", re.IGNORECASE), "Computer Vision"),
    (re.compile(r"humanoid|manipulation", re.IGNORECASE), "Robotics"),
    (re.compile(r"generative|generation", re.IGNORECASE), "Generative AI"),
    (re.compile(r"graph.neural|gnn", re.IGNORECASE), "Machine Learning"),
    (re.compile(r"safety|alignment", re.IGNORECASE), "AI Safety"),
    (re.compile(r"embedding|retrieval", re.IGNORECASE), "RAG / Search"),
    (re.compile(r"fine.?tun|transfer|adapter|lora|qlora|peft", re.IGNORECASE), "Fine-tuning"),
    (re.compile(r"dataset|benchmark|evaluation", re.IGNORECASE), "Data & Evaluation"),
    # Catch model IDs with GPT/LLAMA prefix-lowercase pattern
    (re.compile(r"gpt|llama", re.IGNORECASE), "LLM"),
    (re.compile(r"neural|tensor", re.IGNORECASE), "Machine Learning"),
    (re.compile(r"sam\d|splatting|autopartgen", re.IGNORECASE), "Computer Vision"),
    (re.compile(r"reasoning", re.IGNORECASE), "LLM"),
    (re.compile(r"optimization|optimizer", re.IGNORECASE), "Machine Learning"),
    (re.compile(r"longcat|marlin|moebius|bernini", re.IGNORECASE), "Computer Vision"),
    (re.compile(r"edit|vae", re.IGNORECASE), "Computer Vision"),
    (re.compile(r"q[468]\b", re.IGNORECASE), "Efficiency"),
    (re.compile(r"gemma", re.IGNORECASE), "LLM"),
    (re.compile(r"forecast|weather", re.IGNORECASE), "Machine Learning"),
    (re.compile(r"vl\b", re.IGNORECASE), "Computer Vision"),
    (re.compile(r"gliner|ner\b", re.IGNORECASE), "NLP"),
]

# pipeline_tag → category mapping for HuggingFace models.
# Checked before keyword rules so structured metadata takes priority.
_PIPELINE_TAG_MAP: dict[str, str] = {
    "text-generation": "LLM",
    "text-to-image": "Computer Vision",
    "image-to-image": "Computer Vision",
    "image-text-to-text": "Computer Vision",
    "image-to-3d": "Computer Vision",
    "image-feature-extraction": "Computer Vision",
    "image-classification": "Computer Vision",
    "image-to-text": "Computer Vision",
    "image-to-video": "Computer Vision",
    "image-segmentation": "Computer Vision",
    "object-detection": "Computer Vision",
    "video-classification": "Computer Vision",
    "video-to-video": "Computer Vision",
    "visual-question-answering": "Computer Vision",
    "zero-shot-image-classification": "Computer Vision",
    "depth-estimation": "Computer Vision",
    "text-to-video": "Computer Vision",
    "any-to-any": "Generative AI",
    "text-to-speech": "Audio/Speech",
    "text-to-audio": "Audio/Speech",
    "automatic-speech-recognition": "Audio/Speech",
    "audio-to-audio": "Audio/Speech",
    "audio-classification": "Audio/Speech",
    "sentence-similarity": "NLP",
    "feature-extraction": "NLP",
    "token-classification": "NLP",
    "text-classification": "NLP",
    "fill-mask": "NLP",
    "zero-shot-classification": "NLP",
    "summarization": "NLP",
    "document-question-answering": "RAG / Search",
    "table-question-answering": "RAG / Search",
    "question-answering": "RAG / Search",
    "reinforcement-learning": "Reinforcement Learning",
    "time-series-forecasting": "Machine Learning",
}


class RuleClassifier(AbstractClassifier):
    """Keyword-based classifier that does not require any external API.

    Categories are assigned by scanning the article's ``title`` and
    ``summary`` for predefined keyword patterns.  The first matching rule
    wins; if no rule matches, the article is labelled "Uncategorized".

    The article's ``summary`` field is preserved (truncated to 200 chars if
    longer).  This classifier never raises ``ClassificationError``.
    """

    def classify(self, article: Article) -> tuple[str, str]:
        category = self._classify_by_pipeline_tag(article)
        if category is not None:
            summary = (article.summary or article.title or "")[:200]
            logger.debug("RuleClassifier (pipeline_tag): %r → %s", article.title, category)
            return category, summary

        source_text = f"{article.title or ''} {article.summary or ''}"
        category = "Uncategorized"
        for pattern, label in _KEYWORD_RULES:
            if pattern.search(source_text):
                category = label
                break
        summary = (article.summary or article.title or "")[:200]
        logger.debug("RuleClassifier: %r → %s", article.title, category)
        return category, summary

    @staticmethod
    def _classify_by_pipeline_tag(article: Article) -> str | None:
        if not article.source or "huggingface" not in article.source:
            return None
        raw_data = article.raw
        if not isinstance(raw_data, dict):
            return None
        inner = raw_data.get("raw", {})
        if not isinstance(inner, dict):
            return None
        pt = inner.get("pipeline_tag")
        if not isinstance(pt, str):
            return None
        return _PIPELINE_TAG_MAP.get(pt)
