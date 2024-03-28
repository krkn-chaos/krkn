FROM bitnami/kubectl:1.20.9 as kubectl
FROM python:3.9
WORKDIR /app
RUN pip3 install --upgrade pip
COPY config config/
COPY requirements.txt .
RUN mkdir -p /app/logs
RUN pip3 install -r requirements.txt

COPY --from=kubectl /opt/bitnami/kubectl/bin/kubectl /usr/local/bin/

COPY swagger_api.py .
ENV PYTHONUNBUFFERED=1

RUN curl -fsSLO https://get.docker.com/builds/Linux/x86_64/docker-17.03.1-ce.tgz && tar --strip-components=1 -xvzf docker-17.03.1-ce.tgz -C /usr/local/bin

RUN apt-get update && apt-get install -y podman

COPY aichaos-0.0.1-py3-none-any.whl .
RUN pip3 install aichaos-0.0.1-py3-none-any.whl
CMD ["python3", "swagger_api.py"]
