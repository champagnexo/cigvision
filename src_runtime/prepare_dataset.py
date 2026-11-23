# -*- coding: utf-8 -*-
"""
Crop photos to the detection area (same crop as runtime.py) and split them
into train/val folders for YOLO classification.

Input : ../Images/Originals/butt/       and  ../Images/Originals/not_butt/
Output: ../Dataset/train|val/butt|not_butt/

Images that already have the crop size (for example the ones runtime.py saved
in ../Debug) are copied without cropping again.
"""
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import argparse
import glob
import random

import cv2

from CConfig import CConfig

CLASSES = ("butt", "not_butt")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="../Images/Originals")
    ap.add_argument("--dst", default="../Dataset")
    ap.add_argument("--val", type=float, default=0.2, help="fraction used for validation")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    r = CConfig().GetDetectionCroppingArea()
    x0, y0, x1, y1 = r["crop_x"], r["crop_y"], r["crop_w"], r["crop_h"]
    crop_size = (y1 - y0, x1 - x0)  # (h, w)
    random.seed(args.seed)

    for cls in CLASSES:
        files = []
        for ext in ("png", "jpg", "jpeg"):
            files += glob.glob(os.path.join(args.src, cls, f"*.{ext}"))
        files.sort()
        if not files:
            print(f"WARNING: no images in {os.path.join(args.src, cls)}")
            continue
        random.shuffle(files)
        n_val = max(1, int(len(files) * args.val))

        done = 0
        for i, f in enumerate(files):
            img = cv2.imread(f)
            if img is None:
                continue
            if img.shape[:2] == crop_size:
                crop = img
            elif img.shape[0] >= y1 and img.shape[1] >= x1:
                crop = img[y0:y1, x0:x1]
            else:
                print(f"skip {f}: size {img.shape[:2]} too small for crop")
                continue
            split = "val" if i < n_val else "train"
            out_dir = os.path.join(args.dst, split, cls)
            os.makedirs(out_dir, exist_ok=True)
            name = os.path.splitext(os.path.basename(f))[0] + ".jpg"
            cv2.imwrite(os.path.join(out_dir, name), crop)
            done += 1
        print(f"{cls}: {done} images ({n_val} val)")


if __name__ == "__main__":
    main()
