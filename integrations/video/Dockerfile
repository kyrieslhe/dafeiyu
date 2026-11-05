FROM python@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30
COPY *.whl /wheels/
RUN python -m pip install --disable-pip-version-check --no-cache-dir --no-index --no-deps /wheels/*.whl && rm -rf /wheels
COPY decode.py /opt/dafeiyu/decode.py
USER 65534:65534
ENTRYPOINT ["python", "/opt/dafeiyu/decode.py"]
