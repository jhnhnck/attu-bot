FROM python:3.12-bookworm
ENV TZ="America/New_York"
ENV FORCE_COLOR=1

# copy files and install deps
RUN mkdir /app
WORKDIR /app
COPY ./requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN printf 'BUILD_TIME="%s"\n' "$(date)" >> /app/.env

# add runtime user and change perms
RUN useradd --home-dir /app --uid 1000 doom
RUN chown -Rc doom:doom /app
