import re
from collections import Counter

from app.models.conferences import AnalyzeConferenceBody, AnalyzeConferenceData, ConferencePaperSnapshot
from app.models.papers import (
    ComparePdfArticlesBody,
    ComparePdfArticlesData,
    ComparePdfPaper,
    ExtractPaperBody,
    ExtractPaperData,
    ReadPdfArticleData,
    ReadPdfArticleMetadata,
    SummarizePaperBody,
    SummarizePaperData,
)


def _truncate(value: str, max_chars: int) -> str:
    return value if len(value) <= max_chars else value[: max_chars - 3].rstrip() + "..."


def _split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text).strip()) if part.strip()]


def _top_keywords(text: str, limit: int = 6) -> list[str]:
    stopwords = {"the", "and", "for", "with", "that", "this", "from", "into", "using", "paper", "model", "approach", "data"}
    words = re.findall(r"[a-z][a-z0-9-]{3,}", text.lower())
    counts = Counter(word for word in words if word not in stopwords)
    return [word for word, _ in counts.most_common(limit)]


def summarize_paper_mock(input_data: SummarizePaperBody) -> SummarizePaperData:
    sentences = _split_sentences(input_data.text)
    max_short = 280 if input_data.mode == "short" else 720
    return SummarizePaperData(
        title=input_data.title,
        problem=_truncate(sentences[0] if sentences else "Mock mode inferred the problem from a short excerpt.", 500),
        method=_truncate(sentences[1] if len(sentences) > 1 else "Mock mode had limited evidence about the method.", 500),
        contribution=_truncate(sentences[2] if len(sentences) > 2 else "Mock mode suggests the contribution comes from the central claim in the text.", 500),
        summary_short=_truncate("Mock summary: " + (" ".join(sentences[:2]) or input_data.text), max_short),
        confidence_notes="Generated in MOCK_OPENAI mode. This response is deterministic and intended for local testing.",
    )


def extract_paper_mock(input_data: ExtractPaperBody) -> ExtractPaperData:
    datasets = list(dict.fromkeys(re.findall(r"\b(ImageNet|COCO|KITTI|MIMIC|PubMed|TCGA)\b", input_data.text, flags=re.IGNORECASE)))
    metrics = list(dict.fromkeys(re.findall(r"\b(F1|IoU|mAP|accuracy|precision|recall|AUC|BLEU|ROUGE)\b", input_data.text, flags=re.IGNORECASE)))
    return ExtractPaperData(
        title=input_data.title,
        keywords=_top_keywords(input_data.text),
        datasets=datasets,
        metrics=metrics,
        limitations=["Generated in MOCK_OPENAI mode, so extracted fields are heuristic rather than model-based."],
    )


def analyze_conference_mock(input_data: AnalyzeConferenceBody, papers: list[ConferencePaperSnapshot], total_discovered: int) -> AnalyzeConferenceData:
    themes = Counter()
    for paper in papers:
        themes.update(_top_keywords(f"{paper.title} {paper.excerpt}", 3))
    common_themes = [theme for theme, _ in themes.most_common(5)]
    notable = [f"{paper.title} stands out in mock mode because it was included in the sampled subset." for paper in papers[:3]]
    return AnalyzeConferenceData(
        conference=input_data.conference,
        sourceUrl=str(input_data.source_url),
        totalPapersDiscovered=total_discovered,
        papersAnalyzed=len(papers),
        papers=papers,
        overview=f"Mock conference summary for {input_data.conference}: this response was generated locally from parsed page content without calling OpenAI.",
        keyFindings=[
            f"Mock mode analyzed {len(papers)} sampled paper pages out of {total_discovered} discovered links.",
            f"Recurring topics include {', '.join(common_themes)}." if common_themes else "No strong recurring keywords were found in mock mode.",
        ],
        commonThemes=common_themes,
        notablePapers=notable,
        limitations=["Generated in MOCK_OPENAI mode.", "Conference synthesis is based on lightweight keyword heuristics rather than a language model."],
    )


def make_pdf_read_mock(title: str | None, pdf_url: str, text: str, max_chars: int) -> ReadPdfArticleData:
    limited = text[:max_chars]
    return ReadPdfArticleData(
        title=title,
        pdfUrl=pdf_url,
        pageCount=1,
        text=limited,
        totalCharacters=len(text),
        truncated=len(text) > len(limited),
        metadata=ReadPdfArticleMetadata(author=None, subject=None, keywords=_top_keywords(text)),
    )


def compare_pdf_articles_mock(input_data: ComparePdfArticlesBody, left: ReadPdfArticleData, right: ReadPdfArticleData) -> ComparePdfArticlesData:
    left_keywords = set(_top_keywords(left.text, 8))
    right_keywords = set(_top_keywords(right.text, 8))
    similarities = [f"Both papers discuss {word}." for word in list(left_keywords & right_keywords)[:5]] or ["Mock mode found only weak overlap between the extracted excerpts."]
    differences = [f"{left.title or 'Paper A'} emphasizes {word}." for word in list(left_keywords - right_keywords)[:3]]
    differences += [f"{right.title or 'Paper B'} emphasizes {word}." for word in list(right_keywords - left_keywords)[:3]]
    return ComparePdfArticlesData(
        focus=input_data.focus,
        papers=[
            ComparePdfPaper(title=left.title, pdfUrl=str(left.pdf_url), pageCount=left.page_count, truncated=left.truncated),
            ComparePdfPaper(title=right.title, pdfUrl=str(right.pdf_url), pageCount=right.page_count, truncated=right.truncated),
        ],
        overview=f"Mock comparison of {left.title or 'paper A'} and {right.title or 'paper B'} based on extracted PDF text.",
        similarities=similarities,
        differences=differences,
        recommendation=(f"Use the focus '{input_data.focus}' to decide which paper aligns better with your review question." if input_data.focus else "Inspect the original PDFs for methodology and evaluation details before using this comparison in a review article."),
        limitations=["Generated in MOCK_OPENAI mode.", "The comparison uses heuristic keyword overlap rather than full semantic reasoning."],
    )
