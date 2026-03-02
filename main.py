import argparse
import os
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from gui.main_window import MainWindow


def _collect_pdfs(paths: list) -> list:
    """Expand directories to contained PDF files (recursive)."""
    result = []
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                for f in sorted(files):
                    if f.lower().endswith(".pdf"):
                        result.append(os.path.join(root, f))
        elif p.lower().endswith(".pdf"):
            result.append(p)
        else:
            print(f"Warning: skipping {p!r} — not a PDF or directory", file=sys.stderr)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pdfcompare-gui",
        description="PDFCompare GUI — compare a target PDF against reference PDFs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--target",
        metavar="PDF",
        default=None,
        help="Target PDF to pre-load into the GUI",
    )
    parser.add_argument(
        "--refs",
        nargs="+",
        metavar="PDF_OR_DIR",
        default=[],
        help="Reference PDFs or directories to pre-load (searched recursively for *.pdf)",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Automatically start the comparison after the window opens",
    )

    # Qt consumes its own flags (e.g. --display, --style) from sys.argv, so
    # let argparse see only the unrecognised remainder after Qt has had its pick.
    # We achieve this by parsing known args only.
    args, _ = parser.parse_known_args()

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    if args.target or args.refs:
        ref_files = _collect_pdfs(args.refs)
        # Target must be a single PDF file — reject directories.
        target = None
        if args.target:
            t = os.path.abspath(args.target)
            if os.path.isfile(t) and t.lower().endswith(".pdf"):
                target = t
            else:
                print(
                    f"Warning: --target {args.target!r} is not a PDF file, ignored.",
                    file=sys.stderr,
                )
        refs = [os.path.abspath(p) for p in ref_files]
        QTimer.singleShot(0, lambda: window.load_files(target, refs, auto_run=args.run))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
