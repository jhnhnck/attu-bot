FROM python:3.11-alpine
RUN mkdir /app
WORKDIR /app
COPY ./requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN printf 'BUILD_TIME="%s"\n' "$(date)" >> /app/.env
