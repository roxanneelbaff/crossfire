"""Entry point: `python -m crossfire` or the `crossfire` console script."""

from .app import app


def main():
    app.run(debug=True, port=5000)


if __name__ == "__main__":
    main()
