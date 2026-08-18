FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY magick ./magick
RUN pip install --no-cache-dir .

# CSVs are mounted at /data; every setting can also come from MAGICK_* env vars.
WORKDIR /data
ENTRYPOINT ["magick"]
CMD ["--help"]
