FROM lscr.io/linuxserver/webtop:ubuntu-xfce

ARG OBSIDIAN_VERSION=1.12.7

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends wget ca-certificates \
    && wget -O /tmp/obsidian.deb "https://github.com/obsidianmd/obsidian-releases/releases/download/v${OBSIDIAN_VERSION}/obsidian_${OBSIDIAN_VERSION}_amd64.deb" \
    && apt-get install -y --no-install-recommends /tmp/obsidian.deb \
    && rm -f /tmp/obsidian.deb \
    && rm -rf /var/lib/apt/lists/*

VOLUME ["/vault"]
