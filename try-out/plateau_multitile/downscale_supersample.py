"""
render_multitile.py がSUPERSAMPLE倍で書き出した画像を、tilecutterに渡す
最終サイズ(width x height)へLANCZOSで高品質縮小する。
ソースの解像度自体は増えないが、ジャギー/モアレを抑えられる。
"""
import argparse

from PIL import Image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    args = parser.parse_args()

    img = Image.open(args.image).convert("RGBA")
    resized = img.resize((args.width, args.height), Image.LANCZOS)
    resized.save(args.image)
    print(f"downscaled {img.size} -> {resized.size}: {args.image}")


if __name__ == "__main__":
    main()
