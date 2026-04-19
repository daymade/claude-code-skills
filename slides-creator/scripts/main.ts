#!/usr/bin/env bun
/**
 * Post-processing: assemble deliverables from generated slides
 *
 * After baoyu-slide-deck generates PNGs, this script:
 * 1. Validates the slide sequence (aspect ratio, naming, gaps)
 * 2. Extracts structured speaker notes from 03-prompts/
 * 3. Generates PDF + PPTX in 01-成品/
 *
 * This does NOT generate images — image generation is delegated to baoyu-slide-deck.
 * Post-processing handles: validation, notes extraction, and assembly into deliverables.
 *
 * Usage:
 *   bun main.ts --project /path/to/slide-deck/project-name
 */

import { $ } from "bun";
import { existsSync } from "fs";
import { resolve, basename } from "path";

interface Args {
  projectDir: string;
}

function parseArgs(): Args {
  const idx = process.argv.indexOf("--project");
  if (idx === -1 || !process.argv[idx + 1]) {
    console.error("Usage: bun main.ts --project /path/to/slide-deck/project-name");
    process.exit(1);
  }
  return { projectDir: resolve(process.argv[idx + 1]) };
}

async function main() {
  const { projectDir } = parseArgs();
  const projectName = basename(projectDir);

  const slidesDir = `${projectDir}/02-slides`;
  const outputDir = `${projectDir}/01-成品`;

  if (!existsSync(slidesDir)) {
    console.error(`Slides directory not found: ${slidesDir}`);
    process.exit(1);
  }

  if (!existsSync(outputDir)) {
    console.log(`Creating output directory: ${outputDir}`);
    await $`mkdir -p ${outputDir}`;
  }

  // Validate slides
  console.log("Validating slides...");
  const { stdout } = await $`uv run ${import.meta.dir}/validate_slides.py --slides ${slidesDir}`;
  const result = JSON.parse(stdout.toString());

  if (result.status === "FAILED") {
    console.error("Validation failed:", result.issues);
    process.exit(1);
  }
  if (result.warnings.length > 0) {
    console.warn("Warnings:", result.warnings);
  }
  console.log(`Validation passed: ${result.slide_count} slides`);

  // Extract speaker notes
  const promptsDir = `${projectDir}/03-prompts`;
  const notesPath = `${projectDir}/speaker-notes.md`;
  if (existsSync(promptsDir)) {
    console.log(`Extracting speaker notes: ${notesPath}`);
    await $`uv run ${import.meta.dir}/extract_notes.py --prompts ${promptsDir} --output ${notesPath}`;
  }

  // Generate PDF
  const pdfPath = `${outputDir}/${projectName}.pdf`;
  console.log(`Generating PDF: ${pdfPath}`);
  await $`uv run ${import.meta.dir}/merge_to_pdf.py --slides ${slidesDir} --output ${pdfPath}`;

  // Generate PPTX (with speaker notes from 03-prompts/)
  const pptxPath = `${outputDir}/${projectName}.pptx`;
  console.log(`Generating PPTX: ${pptxPath}`);
  if (existsSync(promptsDir)) {
    await $`uv run ${import.meta.dir}/merge_to_pptx.py --slides ${slidesDir} --output ${pptxPath} --prompts ${promptsDir}`;
  } else {
    await $`uv run ${import.meta.dir}/merge_to_pptx.py --slides ${slidesDir} --output ${pptxPath}`;
  }

  console.log("\nPost-processing complete!");
  console.log(`Deliverables in ${outputDir}:`);
  console.log(`  - ${projectName}.pdf`);
  console.log(`  - ${projectName}.pptx`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
