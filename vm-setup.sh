#!/bin/bash

curl https://pyenv.run | bash

sudo apt update
sudo apt install -y build-essential libssl-dev zlib1g-dev \
                 libbz2-dev libreadline-dev libsqlite3-dev curl \
                 libncursesw5-dev xz-utils tk-dev libxml2-dev \
                 libxmlsec1-dev libffi-dev liblzma-dev

echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
eval "$(pyenv init -)"' >> ~/.bashrc

source ~/.bashrc

pyenv install 3.11
pyenv global 3.11
