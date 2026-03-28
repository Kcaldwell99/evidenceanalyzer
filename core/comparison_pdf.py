import os
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def classify_similarity(score: float) -> str:
    if score >= 90:
        return "High Confidence Match"
    elif score >= 75:
        return "Strong Indication of Common Source"
    elif score >= 60:
        return "Possible Relationship"
    return "Inconclusive"


def wrap_text(text, max_chars=95):
    """
    Simple line wrapper for ReportLab drawString output.
    """
    if not text:
        return []

    words = str(text).split()
    lines = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip()
        if len(test) <= max_chars:
            current = test
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def draw_wrapped_text(c, text, x, y, max_chars=95, line_height=14):
    """
    Draw wrapped text and return updated y position.
    """
    lines = wrap_text(text, max_chars=max_chars)
    for line in lines:
        c.drawString(x, y, line)
        y -= line_height
    return y


def draw_section_heading(c, heading, x, y):
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, heading)
    c.setFont("Helvetica", 10)
    return y - 18


def new_page_if_needed(c, y, min_y=72):
    if y < min_y:
        c.showPage()
        c.setFont("Helvetica", 10)
        return 750
    return y


def generate_comparison_pdf(comparison_result, output_path):
    """
    comparison_result expected structure:

    {
        "suspect_file": "suspect.jpg",
        "reference_file": "reference.jpg",
        "suspect_hash": "abc123...",
        "reference_hash": "def456...",
        "suspect_phash": "ffeeaa...",
        "reference_phash": "ffeeab...",
        "similarity_score": 92.4,
        "classification": "High Confidence Match",   # optional
        "phash_distance": 4,                         # optional
        "sha256_match": False,                       # optional
        "differences": [
            "Resolution differs between the compared images.",
            "Minor compression artifacts are present in the suspect file."
        ],
        "analysis_date": "2026-03-26 16:30:00"       # optional
    }
    """
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter
    y = 750

    suspect_file = comparison_result.get("suspect_file", "Unknown")
    reference_file = comparison_result.get("reference_file", "Unknown")
    suspect_hash = comparison_result.get("suspect_hash", "Not Available")
    reference_hash = comparison_result.get("reference_hash", "Not Available")
    suspect_phash = comparison_result.get("suspect_phash", "Not Available")
    reference_phash = comparison_result.get("reference_phash", "Not Available")
    similarity_score = float(comparison_result.get("similarity_score", 0))
    classification = comparison_result.get("classification") or classify_similarity(similarity_score)
    phash_distance = comparison_result.get("phash_distance", "Not Available")
    sha256_match = comparison_result.get("sha256_match", None)
    differences = comparison_result.get("differences", [])

    analysis_date = comparison_result.get(
        "analysis_date",
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, "Digital Image Comparison Report")
    y -= 28

    c.setFont("Helvetica", 10)
    c.drawString(50, y, f"Analysis Date: {analysis_date}")
    y -= 24

    # Section 1
    y = draw_section_heading(c, "1. File Identification", 50, y)
    y = new_page_if_needed(c, y)

    c.drawString(60, y, f"Suspect File: {suspect_file}")
    y -= 14
    c.drawString(60, y, f"Reference File: {reference_file}")
    y -= 14

    y = draw_wrapped_text(c, f"Suspect SHA-256: {suspect_hash}", 60, y, max_chars=88)
    y = draw_wrapped_text(c, f"Reference SHA-256: {reference_hash}", 60, y, max_chars=88)
    y = draw_wrapped_text(c, f"Suspect pHash: {suspect_phash}", 60, y, max_chars=88)
    y = draw_wrapped_text(c, f"Reference pHash: {reference_phash}", 60, y, max_chars=88)

    y -= 8
    y = new_page_if_needed(c, y)

    # Section 2
    y = draw_section_heading(c, "2. Comparison Summary", 50, y)
    y = new_page_if_needed(c, y)

    c.drawString(60, y, f"Similarity Score: {similarity_score:.2f}%")
    y -= 14
    c.drawString(60, y, f"Match Classification: {classification}")
    y -= 24

    # Section 3
    y = draw_section_heading(c, "3. Technical Analysis", 50, y)
    y = new_page_if_needed(c, y)

    technical_intro = (
        "The comparison incorporates both file-level and image-level forensic indicators, "
        "including cryptographic hash analysis, perceptual hash comparison, and structural "
        "image similarity evaluation."
    )
    y = draw_wrapped_text(c, technical_intro, 60, y)
    y -= 8

    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, y, "A. Hash Analysis")
    y -= 14
    c.setFont("Helvetica", 10)

    if sha256_match is True:
        sha_text = (
            "The SHA-256 hash values are identical. This indicates that the compared files are "
            "bit-for-bit exact copies."
        )
    elif sha256_match is False:
        sha_text = (
            "The SHA-256 hash values are not identical. This indicates that the compared files "
            "are not exact binary duplicates."
        )
    else:
        sha_text = "SHA-256 comparison data was reviewed as part of the file-level assessment."

    y = draw_wrapped_text(c, sha_text, 70, y)
    y -= 4

    phash_text = (
        f"The perceptual hash distance is {phash_distance}. Lower distances generally indicate "
        "greater visual similarity between the compared images."
    )
    y = draw_wrapped_text(c, phash_text, 70, y)
    y -= 10
    y = new_page_if_needed(c, y)

    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, y, "B. Visual Similarity Analysis")
    y -= 14
    c.setFont("Helvetica", 10)

    if similarity_score >= 90:
        visual_text = (
            "The compared images exhibit a high degree of structural similarity. The observed "
            "features are consistent with the same source image or a modified version of that image."
        )
    elif similarity_score >= 75:
        visual_text = (
            "The compared images exhibit substantial structural similarity. The observed features "
            "suggest a common source relationship, potentially with minor edits, recompression, "
            "resizing, or format conversion."
        )
    elif similarity_score >= 60:
        visual_text = (
            "The compared images exhibit moderate structural similarity. The findings suggest a "
            "possible relationship, but the available indicators are not sufficiently strong to "
            "support a more definitive conclusion."
        )
    else:
        visual_text = (
            "The compared images do not exhibit a sufficiently strong degree of structural "
            "similarity to support a conclusion of likely common origin."
        )

    y = draw_wrapped_text(c, visual_text, 70, y)
    y -= 18
    y = new_page_if_needed(c, y)

    # Section 4
    y = draw_section_heading(c, "4. Observed Differences", 50, y)
    y = new_page_if_needed(c, y)

    if differences:
        for diff in differences:
            y = new_page_if_needed(c, y)
            y = draw_wrapped_text(c, f"- {diff}", 60, y)
    else:
        default_diff = (
            "No significant distinguishing differences were recorded beyond those ordinarily "
            "associated with potential recompression, resizing, or metadata variation."
        )
        y = draw_wrapped_text(c, default_diff, 60, y)

    y -= 12
    y = new_page_if_needed(c, y)

    # Section 5
    y = draw_section_heading(c, "5. Forensic Interpretation", 50, y)
    y = new_page_if_needed(c, y)

    interpretation_intro = (
        "The similarity assessment is based on converging indicators rather than any single metric. "
        "This assessment considers both file-level and image-level characteristics."
    )
    y = draw_wrapped_text(c, interpretation_intro, 60, y)
    y -= 8

    if classification == "High Confidence Match":
        interpretation = (
            "The examined files exhibit a high degree of similarity across multiple forensic "
            "indicators. The findings support the conclusion that the suspect image is likely "
            "derived from the same source as the reference image, or represents a modified "
            "version of that image."
        )
    elif classification == "Strong Indication of Common Source":
        interpretation = (
            "The compared files demonstrate substantial similarity across multiple forensic "
            "indicators. The findings strongly suggest a common source relationship, although "
            "minor variations are present."
        )
    elif classification == "Possible Relationship":
        interpretation = (
            "The observed similarities suggest a possible relationship between the compared files; "
            "however, the available indicators are insufficient to conclusively determine a common origin."
        )
    else:
        interpretation = (
            "The available indicators do not support a reliable conclusion that the compared "
            "files share a common source."
        )

    y = draw_wrapped_text(c, interpretation, 60, y)
    y -= 12
    y = new_page_if_needed(c, y)

    # Section 6
    y = draw_section_heading(c, "6. Methodology", 50, y)
    y = new_page_if_needed(c, y)

    methodology = (
        "This analysis applies a multi-factor forensic methodology combining cryptographic hashing, "
        "perceptual hashing, and comparative image structure evaluation. These techniques are widely "
        "used in digital forensic examinations to assess file identity and similarity."
    )
    y = draw_wrapped_text(c, methodology, 60, y)
    y -= 12
    y = new_page_if_needed(c, y)

    # Section 7
    y = draw_section_heading(c, "7. Limitations", 50, y)
    y = new_page_if_needed(c, y)

    limitations = (
        "This report does not determine authorship, ownership, or legal infringement. Metadata may "
        "be incomplete, absent, or altered. Conclusions are based solely on the digital characteristics "
        "of the submitted files."
    )
    y = draw_wrapped_text(c, limitations, 60, y)
    y -= 12
    y = new_page_if_needed(c, y)

    # Section 8
    y = draw_section_heading(c, "8. Reproducibility Statement", 50, y)
    y = new_page_if_needed(c, y)

    reproducibility = (
        "All analysis steps are reproducible using identical input files within the Evidentix™ system."
    )
    y = draw_wrapped_text(c, reproducibility, 60, y)
    y -= 12
    y = new_page_if_needed(c, y)

    # Section 9
    y = draw_section_heading(c, "9. Final Conclusion", 50, y)
    y = new_page_if_needed(c, y)

    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, y, f"Conclusion: {classification}")
    y -= 16
    c.setFont("Helvetica", 10)

    if classification == "High Confidence Match":
        final_conclusion = (
            "The totality of forensic indicators supports the conclusion that the suspect image "
            "is derived from the same source as the reference image."
        )
    elif classification == "Strong Indication of Common Source":
        final_conclusion = (
            "The totality of forensic indicators strongly supports a common source relationship "
            "between the compared images."
        )
    elif classification == "Possible Relationship":
        final_conclusion = (
            "The compared images exhibit indicators consistent with a possible relationship, "
            "but the findings remain inconclusive."
        )
    else:
        final_conclusion = (
            "The available indicators are insufficient to support a conclusion of common origin."
        )

    y = draw_wrapped_text(c, final_conclusion, 60, y)

    c.save()
    return output_path