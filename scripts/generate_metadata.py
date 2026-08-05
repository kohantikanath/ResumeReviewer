"""Generate metadata.xlsx from calibration PDF fixtures."""

from pathlib import Path

from app.metadata import build_metadata_from_pdfs, save_metadata

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "samples"


def main() -> None:
    pdfs = sorted(FIXTURES.glob("*.pdf"))
    df = build_metadata_from_pdfs(pdfs)
    out = FIXTURES / "metadata.xlsx"
    save_metadata(df, out)
    print(f"Wrote {out}")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
