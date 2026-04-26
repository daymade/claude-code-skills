#!/usr/bin/env python3
"""
Extract images from PDF files with metadata using PyMuPDF.

Features:
- Extracts all images with page and position metadata
- Generates JSON metadata file for each image
- Supports markdown reference generation
- Optional DPI control for quality

Usage:
    uv run --with pymupdf scripts/extract_pdf_images.py document.pdf
    uv run --with pymupdf scripts/extract_pdf_images.py document.pdf -o ./images
    uv run --with pymupdf scripts/extract_pdf_images.py document.pdf --markdown refs.md

Examples:
    # Basic extraction
    uv run --with pymupdf scripts/extract_pdf_images.py document.pdf

    # With custom output and markdown references
    uv run --with pymupdf scripts/extract_pdf_images.py doc.pdf -o assets --markdown images.md
"""

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


@dataclass
class ImageMetadata:
    """Metadata for an extracted image."""
    filename: str
    page: int  # 1-indexed
    index: int  # Image index on page (1-indexed)
    width: int  # Original width in pixels
    height: int  # Original height in pixels
    x: float  # X position on page (points)
    y: float  # Y position on page (points)
    bbox_width: float  # Width on page (points)
    bbox_height: float  # Height on page (points)
    size_bytes: int
    format: str  # png, jpg, etc.
    colorspace: str  # RGB, CMYK, Gray
    bits_per_component: int


def extract_images(
    pdf_path: Path,
    output_dir: Path,
    markdown_file: Optional[Path] = None
) -> list[ImageMetadata]:
    """
    Extract all images from a PDF file with metadata.

    Args:
        pdf_path: Path to the PDF file
        output_dir: Directory to save extracted images
        markdown_file: Optional path to write markdown references

    Returns:
        List of ImageMetadata for each extracted image
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("Error: PyMuPDF not installed. Run with:")
        print('  uv run --with pymupdf scripts/extract_pdf_images.py <pdf_path>')
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    extracted: list[ImageMetadata] = []
    markdown_refs: list[str] = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images(full=True)

        for img_index, img_info in enumerate(image_list):
            xref = img_info[0]

            try:
                base_image = doc.extract_image(xref)
            except Exception as e:
                print(f"  Warning: Could not extract image xref={xref}: {e}")
                continue

            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            width = base_image.get("width", 0)
            height = base_image.get("height", 0)
            colorspace = base_image.get("colorspace", 0)
            bpc = base_image.get("bpc", 8)

            # Map colorspace number to name
            cs_names = {1: "Gray", 3: "RGB", 4: "CMYK"}
            cs_name = cs_names.get(colorspace, f"Unknown({colorspace})")

            # Get image position on page
            # img_info: (xref, smask, width, height, bpc, colorspace, alt, name, filter, referencer)
            # We need to find the image rect on page
            bbox_x, bbox_y, bbox_w, bbox_h = 0.0, 0.0, 0.0, 0.0

            # Search for image instances on page
            for img_block in page.get_images():
                if img_block[0] == xref:
                    # Found matching image, try to get its rect
                    rects = page.get_image_rects(img_block)
                    if rects:
                        rect = rects[0]  # Use first occurrence
                        bbox_x = rect.x0
                        bbox_y = rect.y0
                        bbox_w = rect.width
                        bbox_h = rect.height
                    break

            # Create descriptive filename
            img_filename = f"img_page{page_num + 1}_{img_index + 1}.{image_ext}"
            img_path = output_dir / img_filename

            # Save image
            with open(img_path, "wb") as f:
                f.write(image_bytes)

            # Create metadata
            metadata = ImageMetadata(
                filename=img_filename,
                page=page_num + 1,
                index=img_index + 1,
                width=width,
                height=height,
                x=round(bbox_x, 2),
                y=round(bbox_y, 2),
                bbox_width=round(bbox_w, 2),
                bbox_height=round(bbox_h, 2),
                size_bytes=len(image_bytes),
                format=image_ext,
                colorspace=cs_name,
                bits_per_component=bpc
            )
            extracted.append(metadata)

            # Generate markdown reference
            alt_text = f"Image from page {page_num + 1}"
            md_ref = f"![{alt_text}]({img_path.name})"
            markdown_refs.append(f"<!-- Page {page_num + 1}, Position: ({bbox_x:.0f}, {bbox_y:.0f}) -->\n{md_ref}")

            print(f"  ✓ {img_filename} ({width}x{height}, {len(image_bytes):,} bytes)")

    doc.close()

    # Write metadata JSON
    metadata_path = output_dir / "images_metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(
            {
                "source": str(pdf_path),
                "image_count": len(extracted),
                "images": [asdict(m) for m in extracted]
            },
            f,
            indent=2
        )
    print(f"\n📋 Metadata: {metadata_path}")

    # Write markdown references if requested
    if markdown_file and markdown_refs:
        markdown_content = f"# Images from {pdf_path.name}\n\n"
        markdown_content += "\n\n".join(markdown_refs)
        markdown_file.parent.mkdir(parents=True, exist_ok=True)
        markdown_file.write_text(markdown_content)
        print(f"📝 Markdown refs: {markdown_file}")

    print(f"\n✅ Total: {len(extracted)} images extracted to {output_dir}/")
    return extracted


def main():
    parser = argparse.ArgumentParser(
        description="Extract images from PDF files with metadata",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic extraction
    uv run --with pymupdf scripts/extract_pdf_images.py document.pdf

    # Custom output directory
    uv run --with pymupdf scripts/extract_pdf_images.py doc.pdf -o ./images

    # With markdown references
    uv run --with pymupdf scripts/extract_pdf_images.py doc.pdf --markdown refs.md

Output:
    Images are saved with descriptive names: img_page1_1.png, img_page2_1.jpg
    Metadata is saved to: images_metadata.json
        """
    )
    parser.add_argument(
        "pdf_path",
        type=Path,
        help="Path to the PDF file"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path("assets"),
        help="Directory to save images (default: ./assets)"
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        help="Generate markdown file with image references"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output metadata as JSON to stdout"
    )

    args = parser.parse_args()

    if not args.pdf_path.exists():
        print(f"Error: File not found: {args.pdf_path}", file=sys.stderr)
        sys.exit(1)

    print(f"📄 Extracting images from: {args.pdf_path}")

    extracted = extract_images(
        args.pdf_path,
        args.output,
        args.markdown
    )

    if args.json:
        print(json.dumps([asdict(m) for m in extracted], indent=2))


if __name__ == "__main__":
    main()
