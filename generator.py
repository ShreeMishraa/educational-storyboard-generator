"""
Brick 3: Master Prompt Builder & PDF Exporter.
Dynamically constructs pure image generation prompts tailored strictly 
to the input script documents and reference PDFs without video studio layout or video-editing terminology.
"""

import os
import re
import json
from fpdf import FPDF


def sanitize_text(text: str) -> str:
    if not text:
        return "NA"
    replacements = {
        '•': '-', '–': '-', '—': '-', '“': '"', '”': '"',
        '‘': "'", '’': "'", '…': '...'
    }
    for orig, repl in replacements.items():
        text = text.replace(orig, repl)
    return text.encode('latin-1', 'replace').decode('latin-1')


def clean_text_descriptors(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\b(clear|lush|ripe|green)\s+\1\b", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def build_image_prompt(panel_spec: dict, global_style_override: str = None) -> str:
    """
    Builds a pure image prompt derived 100% dynamically from the active panel's specifications.
    Focuses strictly on visual art composition, subject, details, and text overlays.
    """
    layout = panel_spec.get("canvas_layout", {})
    vis_desc = clean_text_descriptors(layout.get("visual_description", ""))
    shot_type = panel_spec.get("shot_type", "Mid Shot")
    layout_mode = layout.get("layout_mode", "full_bleed")
    scene_str = (panel_spec.get("scene") or "").upper()
    
    # 1. Dynamic Aesthetic Style Detection (Color vs Monochrome)
    combined_check_text = (vis_desc + " " + (global_style_override or "")).lower()
    is_explicit_monochrome = any(
        k in combined_check_text for k in ["monochrome", "grayscale", "black and white", "line art", "pencil sketch"]
    )

    if is_explicit_monochrome:
        style_anchor = (
            "Aesthetic Style: Fine black and white line-art pencil and ink illustration, crisp graphite linework, "
            "detailed hatching, high contrast, clean white background, 16:9 widescreen image."
        )
    else:
        style_anchor = (
            "Aesthetic Style: High quality 16:9 widescreen educational digital artwork, vivid colors, "
            "crisp graphic illustration, clean lighting, clear visual hierarchy."
        )

    # 2. Image Framing & Composition
    comp_parts = []
    if layout_mode == "split_3way" or "3-way" in vis_desc.lower() or "three-way" in vis_desc.lower():
        comp_parts.append(
            "Composition: 3-way vertical split screen layout divided into three equal side-by-side panels "
            "separated by thin neat black border lines."
        )
    elif layout_mode == "split_2way" or "split" in vis_desc.lower():
        comp_parts.append(
            "Composition: 2-way vertical split screen layout divided into two equal side-by-side panels "
            "separated by a neat dividing line."
        )
    elif layout_mode == "presenter_with_mog_inset" or "MOG" in shot_type:
        comp_parts.append(
            "Composition: Split layout. Left side shows the presenter; right side features a distinct floating "
            "graphic illustration card on a clean background."
        )
    elif shot_type == "Mid Shot":
        comp_parts.append("Composition: Centered mid shot framing with subject clearly in focus.")
    elif shot_type in ["FSA", "Full Screen Graphic", "Title card", "TOS 1"]:
        comp_parts.append(f"Composition: Full screen infographic card layout ({shot_type}) designed for educational clarity.")
    else:
        comp_parts.append(f"Composition: {shot_type} framing with balanced subject placement.")

    # 3. Dynamic Setting & Visual Details
    detail_parts = []
    if scene_str and scene_str != "NA":
        detail_parts.append(f"Setting & Scene: {scene_str}.")
    detail_parts.append(f"Subject & Visual Details: {vis_desc}")

    # 4. On-Screen Text Overlay Badges
    text_directives = []
    tos_items = panel_spec.get("text_overlays", [])
    if tos_items:
        tos_str = " | ".join([clean_text_descriptors(t['text'] if isinstance(t, dict) else t) for t in tos_items])
        text_directives.append(
            f"On-Screen Text Elements: Render clean graphic text box badge displaying EXACT text: \"{tos_str}\". "
            "Typography must be bold, highly legible, and centered within the badge."
        )
    else:
        text_directives.append("On-Screen Text Elements: No text overlays outside specified graphic labels.")

    # 5. Pure Image Constraints
    constraints = [
        "Constraints: High visual clarity, centered composition, no watermarks, no logos, "
        "no camera gear, no video production artifacts, no unintended text."
    ]

    full_prompt_sections = [
        style_anchor,
        " ".join(comp_parts),
        " ".join(detail_parts),
        " ".join(text_directives),
        " ".join(constraints)
    ]

    return "\n".join([s for s in full_prompt_sections if s]).strip()


class StoryboardPromptPDF(FPDF):
    def get_effective_width(self):
        """Calculates page printable width safely across FPDF versions."""
        return self.w - 2 * self.l_margin

    def header(self):
        epw = self.get_effective_width()
        self.set_font('Helvetica', 'B', 14)
        self.cell(epw, 10, 'Master Storyboard Panel Prompts', border=0, ln=1, align='C')
        self.set_font('Helvetica', 'I', 10)
        self.cell(epw, 5, 'Client Approved 16:9 Visual Specifications', border=0, ln=1, align='C')
        self.ln(5)

    def footer(self):
        epw = self.get_effective_width()
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.cell(epw, 10, f'Page {self.page_no()}', border=0, ln=1, align='C')


def generate_prompts_pdf(plan_data: dict, output_pdf_path: str = "output/all_storyboard_prompts.pdf") -> str:
    pdf = StoryboardPromptPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    title = sanitize_text(plan_data.get("title", "Storyboard Script"))
    panels = plan_data.get("panels", [])

    pdf.add_page()
    epw = pdf.get_effective_width()

    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(epw, 8, f"Document: {title}", ln=1)
    pdf.cell(epw, 8, f"Total Panels: {len(panels)}", ln=1)
    pdf.ln(5)

    for panel in panels:
        pid = panel.get("panel_id")
        shot_type = sanitize_text(panel.get("shot_type", "FSA"))
        scene = sanitize_text(panel.get("scene", "NA"))

        presenter = panel.get("presenter", {})
        dialogue = sanitize_text(presenter.get("dialogue", "NA"))
        audio_mode = sanitize_text(presenter.get("audio_mode", "SYNC"))

        layout = panel.get("canvas_layout", {})
        visual_desc = sanitize_text(layout.get("visual_description", ""))

        prompt = sanitize_text(build_image_prompt(panel))

        # Panel Header Box
        pdf.set_x(pdf.l_margin)
        pdf.set_fill_color(230, 230, 230)
        pdf.set_font('Helvetica', 'B', 11)
        pdf.cell(epw, 8, f" PANEL {pid:03d} | Shot: {shot_type} | Scene: {scene}", border=1, fill=True, ln=1)

        pdf.set_font('Helvetica', '', 10)
        if dialogue != "NA":
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(epw, 5, f"Dialogue ({audio_mode}): {dialogue}")
        if visual_desc:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(epw, 5, f"Visual Notes: {visual_desc}")

        tos_items = panel.get("text_overlays", [])
        if tos_items:
            tos_str = " | ".join([sanitize_text(t['text'] if isinstance(t, dict) else t) for t in tos_items])
            pdf.set_font('Helvetica', 'B', 9)
            pdf.set_x(pdf.l_margin)
            pdf.cell(epw, 6, f"TOS Badge: {tos_str}", ln=1)

        pdf.ln(2)
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_x(pdf.l_margin)
        pdf.cell(epw, 5, "COPY-PASTE IMAGE GENERATION PROMPT:", ln=1)

        pdf.set_font('Courier', '', 8)
        pdf.set_fill_color(248, 248, 248)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(epw, 4, prompt, border=1, fill=True)
        pdf.ln(6)

    os.makedirs(os.path.dirname(output_pdf_path) or ".", exist_ok=True)
    pdf.output(output_pdf_path)
    return output_pdf_path