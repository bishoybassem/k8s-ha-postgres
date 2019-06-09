FROM python:3.7.3-slim-stretch

COPY requirements.txt /

RUN pip install -r /requirements.txt

COPY *.py app/

ENTRYPOINT ["python3", "-u", "app/controller.py"]