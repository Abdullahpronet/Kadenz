"""Kadenz command line entry point (v0.1 work in progress)."""
import argparse


def main() -> None:
    p = argparse.ArgumentParser(prog="kadenz", description="Clips + song -> beat-synced After Effects project.")
    p.add_argument("--clips", required=True, help="Folder with video clips")
    p.add_argument("--song", required=True, help="Song file (mp3/wav)")
    p.add_argument("--style", default="velocity", help="Edit style preset")
    p.add_argument("--out", default="edit.jsx", help="Output file")
    args = p.parse_args()
    print(f"Kadenz v0.1 is under construction. Got: {vars(args)}")


if __name__ == "__main__":
    main()
