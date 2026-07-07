"""
四方位キャリブレーション用: レンダリング済み画像にBackImageスロット番号(l=0-3)を
大きく焼き込む。実機で回転させた際にどのスロットがどのマップ方位に対応するかを
直読みするための目印(shinkansen_0のZ回転角ラベル方式と同じ考え方)。
"""
import argparse

from PIL import Image, ImageDraw, ImageFont


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    parser.add_argument("label")
    args = parser.parse_args()

    img = Image.open(args.image).convert("RGBA")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 64)
    except OSError:
        font = ImageFont.load_default(size=64)

    text = args.label
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (img.width - tw) / 2 - bbox[0]
    y = (img.height - th) / 2 - bbox[1]
    draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, 255))
    draw.text((x, y), text, font=font, fill=(255, 255, 0, 255))
    img.save(args.image)
    print(f"labeled {args.image} with '{text}'")


if __name__ == "__main__":
    main()
