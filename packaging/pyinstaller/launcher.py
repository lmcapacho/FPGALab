"""PyInstaller entry point that preserves package-relative imports."""

from fpga_lab.app import main


if __name__ == "__main__":
    main()
