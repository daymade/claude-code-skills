#!/usr/bin/env python3
"""
Extract images from PDF files using PyMuPDF.

Usage:
    uv run --with pymupdf python extract_pdf_images.py <pdf_path> [output_dir]

Examples:
    uv run --with pymupdf python extract_pdf_images.py document.pdf
    uv run --with pymupdf python extract_pdf_images.py document.pdf ./assets

Output:
    Images are saved to output_dir (default: ./assets) with names like:
    - img_page1_1.png
    - img_page2_1.png
"""

import sys
import os

def extract_images(pdf_path: str, output_dir: str = "assets") -> list[str]:
    """
    Extract all images from a PDF file.

    Args:
        pdf_path: Path to the PDF file
        output_dir: Directory to save extracted images

    Returns:
        List of extracted image file paths
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("Error: PyMuPDF not installed. Run with:")
        print('  uv run --with pymupdf python extract_pdf_images.py <pdf_path>')
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    doc = fitz.open(pdf_path)
    extracted_files = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images()

        for img_index, img in enumerate(image_list):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]

            # Create descriptive filename
            img_filename = f"img_page{page_num + 1}_{img_index + 1}.{image_ext}"
            img_path = os.path.join(output_dir, img_filename)

            with open(img_path, "wb") as f:
                f.write(image_bytes)

            extracted_files.append(img_path)
            print(f"Extracted: {img_filename} ({len(image_bytes):,} bytes)")

    doc.close()

    print(f"\nTotal: {len(extracted_files)} images extracted to {output_dir}/")
    return extracted_files


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Extract images from PDF files using PyMuPDF.")
        print()
        print("Usage: python extract_pdf_images.py <pdf_path> [output_dir]")
        print()
        print("Arguments:")
        print("  pdf_path    Path to the PDF file")
        print("  output_dir  Directory to save images (default: ./assets)")
        print()
        print("Example:")
        print("  uv run --with pymupdf python extract_pdf_images.py document.pdf ./assets")
        sys.exit(0 if "--help" in sys.argv or "-h" in sys.argv else 1)

    pdf_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "assets"

    if not os.path.exists(pdf_path):
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    extract_images(pdf_path, output_dir)


if __name__ == "__main__":
    main()
