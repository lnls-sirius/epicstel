# Base image
FROM lnlscon/epics-r3.15.5

MAINTAINER Patricia Nallin <patricia.nallin@lnls.br>
USER root

# set the working directory
WORKDIR /telegram

# copy requirements into the container at /telegram and install needed packages
COPY requirements.txt /telegram
RUN pip3 install -r requirements.txt

# Port 80 available
EXPOSE 80

# Container init
CMD python3 /telegram/tmsg.py $(cat /run/secrets/TELEGRAM_BOT_TOKEN)
