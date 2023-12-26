FROM python:latest

WORKDIR /usr/src/app

RUN pip install paho-mqtt minimalmodbus

COPY *.py ./
COPY README.md .

CMD ["python3", "./swegon-to-mqtt.py"]
