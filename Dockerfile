FROM python:3.12-alpine
ENV TZ="America/New_York"
ENV FORCE_COLOR=1
RUN mkdir /app
WORKDIR /app
COPY ./requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN printf 'BUILD_TIME="%s"\n' "$(date)" >> /app/.env
