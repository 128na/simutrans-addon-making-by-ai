"""
tilecutter (refs/tilecutter) をライブラリとして直接呼び出し、
render_multitile.pyが生成した1枚の合成画像をタイル単位に分割してdat/png/pakを出力する。

tilecutter本体のCLIエントリポイント(main.py -c)はProjectクラスの新旧API不一致で
AttributeErrorになるため使用せず、project.Project + tc.export_cutter/export_writer を
直接呼び出す(内部エンジンをライブラリとして利用する形)。
"""

import argparse
import os
import sys

TILECUTTER_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "refs", "tilecutter")
MAKEOBJ_PATH = r"C:\bin\makeobj.exe"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("images", nargs="+", help="1枚(directions=1)または4枚(d=0..3, directions=4)")
    parser.add_argument("--dims-x", type=int, default=2)
    parser.add_argument("--dims-y", type=int, default=2)
    parser.add_argument("--paksize", type=int, default=128)
    parser.add_argument("--name", default="plateau_multitile")
    parser.add_argument("--dat-lump", required=True)
    parser.add_argument("--outdir", default=os.path.dirname(__file__))
    args = parser.parse_args()

    if len(args.images) not in (1, 4):
        parser.error("images must be 1 or 4 paths")
    directions = len(args.images)

    sys.path.insert(0, TILECUTTER_DIR)
    import wx
    app = wx.App(False)
    import config
    config = config.Config()
    config.path_to_makeobj = MAKEOBJ_PATH
    import project, tc

    def imgnode(path=""):
        return [[{"path": path, "offset": [0, 0]}, {"path": "", "offset": [0, 0]}]]

    images_by_direction = []
    for d in range(4):
        path = args.images[d] if d < directions else ""
        images_by_direction.append([imgnode(path)] + [imgnode() for _ in range(4)])

    props = {
        "images": images_by_direction,
        "transparency": True,
        "dims": {
            "x": args.dims_x, "y": args.dims_y, "z": 1,
            "paksize": args.paksize,
            "directions": directions,
            "frames": 1,
            "seasons": {"snow": 0, "autumn": 0, "winter": 0, "spring": 0},
            "frontimage": 0,
        },
        "files": {
            "datfile_location": f"{args.name}.dat",
            "datfile_write": True,
            "pngfile_location": f"{args.name}.png",
            "pakfile_location": f"{args.name}.pak",
        },
        "dat": {"dat_lump": args.dat_lump},
    }

    proj = project.Project(parent=None, load=props, save_location=args.outdir, saved=True)
    proj.cut_images(tc.export_cutter)
    tc.export_writer(proj, pak_output=True, return_dat=False, write_dat=True)
    print("EXPORT_DONE")


if __name__ == "__main__":
    main()
