"""Extract the exam handout into inexpensive, reusable UTF-8 text assets."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pymupdf


def normalize(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    pages_dir = args.output / "pages"
    pages_dir.mkdir(exist_ok=True)

    document = pymupdf.open(args.pdf)
    pages: list[dict[str, object]] = []
    markdown = [
        "# 2026학년도 2학년 영어 기출문제 학습자료 - 추출 원문",
        "",
        f"- 원본: `{args.pdf.resolve()}`",
        f"- 전체 페이지: {len(document)}",
        "- 용도: 이후 변형 작업에서 PDF를 반복 분석하지 않고 사용할 UTF-8 원문",
        "- 주의: 자동 추출본이므로 중요한 편집 전에는 해당 페이지 이미지와 대조할 것",
        "",
    ]

    for index, page in enumerate(document, start=1):
        # Hancom PDFs already expose a sensible reading order. Geometric sorting
        # inserts layout-only gaps and blank lines, which wastes tokens later.
        text = normalize(page.get_text("text"))
        page_path = pages_dir / f"{index:02d}.txt"
        page_path.write_text(text + "\n", encoding="utf-8")
        pages.append({"page": index, "text": text})
        markdown.extend([f"## 페이지 {index:02d}", "", text, ""])

    (args.output / "source.json").write_text(
        json.dumps(
            {
                "source_pdf": str(args.pdf.resolve()),
                "page_count": len(document),
                "pages": pages,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (args.output / "source.md").write_text("\n".join(markdown), encoding="utf-8")
    print(f"Extracted {len(document)} pages to {args.output.resolve()}")


if __name__ == "__main__":
    main()
