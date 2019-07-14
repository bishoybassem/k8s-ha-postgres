FROM python:3.7.3-slim-stretch

COPY requirements.txt /

RUN pip install -r /requirements.txt

COPY pg_controller /pg_controller
COPY entrypoint.py /

ENTRYPOINT ["python3", "-u", "/entrypoint.py"]