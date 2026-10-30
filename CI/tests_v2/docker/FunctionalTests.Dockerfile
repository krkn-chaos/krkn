ARG KRKN_RUNTIME_IMAGE
FROM ${KRKN_RUNTIME_IMAGE}

ARG PYTHON_VERSION=3.11

USER root
WORKDIR /home/krkn/kraken

RUN python${PYTHON_VERSION} -m venv --system-site-packages /opt/krkn-test-venv \
    && /opt/krkn-test-venv/bin/python -m pip install --no-cache-dir \
        -r /home/krkn/kraken/CI/tests_v2/requirements.txt

ENV KRKN_TEST_KRAKEN_PYTHON=python${PYTHON_VERSION}
ENV KRKN_TEST_COVERAGE=1

USER krkn
ENTRYPOINT ["/opt/krkn-test-venv/bin/python", "-m", "pytest"]
CMD ["CI/tests_v2/", "-v", "--timeout=300", "--reruns=1", "--reruns-delay=5", "--html=CI/tests_v2/report.html", "-n", "auto", "--dist", "loadgroup", "--junitxml=CI/tests_v2/results.xml"]
