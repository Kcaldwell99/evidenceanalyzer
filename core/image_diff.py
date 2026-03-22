import os
import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim


def generate_diff_outputs(image_path_a, image_path_b, output_dir):

    os.makedirs(output_dir, exist_ok=True)

    img_a = cv2.imread(image_path_a)
    img_b = cv2.imread(image_path_b)

    if img_a is None or img_b is None:
        raise ValueError("Could not load one of the images for comparison")

    # normalize dimensions
    h = min(img_a.shape[0], img_b.shape[0])
    w = min(img_a.shape[1], img_b.shape[1])

    img_a = cv2.resize(img_a, (w, h))
    img_b = cv2.resize(img_b, (w, h))

    gray_a = cv2.cvtColor(img_a, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(img_b, cv2.COLOR_BGR2GRAY)

    score, diff = ssim(gray_a, gray_b, full=True)
    diff = (diff * 255).astype("uint8")

    thresh = cv2.threshold(
        diff,
        0,
        255,
        cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU
    )[1]

    contours, _ = cv2.findContours(
        thresh.copy(),
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    marked_a = img_a.copy()
    marked_b = img_b.copy()

    difference_regions = 0

    for contour in contours:

        if cv2.contourArea(contour) < 40:
            continue

        x, y, w_box, h_box = cv2.boundingRect(contour)

        cv2.rectangle(marked_a, (x, y), (x + w_box, y + h_box), (0, 0, 255), 2)
        cv2.rectangle(marked_b, (x, y), (x + w_box, y + h_box), (0, 0, 255), 2)

        difference_regions += 1

    heatmap = cv2.applyColorMap(255 - diff, cv2.COLORMAP_JET)

    side_by_side = np.hstack((marked_a, marked_b))

    # file paths
    diff_map_path = os.path.join(output_dir, "diff_map.png")
    threshold_map_path = os.path.join(output_dir, "threshold_map.png")
    original_marked_path = os.path.join(output_dir, "original_marked.png")
    suspect_marked_path = os.path.join(output_dir, "suspect_marked.png")
    heatmap_path = os.path.join(output_dir, "heatmap.png")
    side_by_side_path = os.path.join(output_dir, "side_by_side.png")

    normalized_original_path = os.path.join(output_dir, "normalized_original.png")
    normalized_suspect_path = os.path.join(output_dir, "normalized_suspect.png")

    cv2.imwrite(diff_map_path, diff)
    cv2.imwrite(threshold_map_path, thresh)
    cv2.imwrite(original_marked_path, marked_a)
    cv2.imwrite(suspect_marked_path, marked_b)
    cv2.imwrite(heatmap_path, heatmap)
    cv2.imwrite(side_by_side_path, side_by_side)

    cv2.imwrite(normalized_original_path, img_a)
    cv2.imwrite(normalized_suspect_path, img_b)

    similarity_percent = round(score * 100, 2)

    if score >= 0.98:
        visual_assessment = "Nearly identical"
    elif score >= 0.95:
        visual_assessment = "Highly similar"
    elif score >= 0.90:
        visual_assessment = "Moderately similar"
    else:
        visual_assessment = "Substantially different"

    return {
        "ssim_score": float(score),
        "similarity_percent": similarity_percent,
        "visual_assessment": visual_assessment,
        "difference_regions": difference_regions,
        "diff_map_path": diff_map_path,
        "threshold_map_path": threshold_map_path,
        "original_marked_path": original_marked_path,
        "suspect_marked_path": suspect_marked_path,
        "heatmap_path": heatmap_path,
        "side_by_side_path": side_by_side_path,
        "normalized_original_path": normalized_original_path,
        "normalized_suspect_path": normalized_suspect_path,
    }