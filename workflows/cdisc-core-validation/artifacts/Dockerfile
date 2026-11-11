# CDISC CORE validation image: Python + the pinned CORE rules engine, from source.
#
# Built by the platform from this carried file (context = the carried
# artifacts); scripts are not copied in, they run from /artifacts. CORE's
# release binaries are x86_64 only and fail on an arm64 builder ("Exec format
# error"), so the engine is installed from the release's source tag instead,
# which runs on either architecture. The tag ships the rules cache and CT
# packages (resources/cache), so no CDISC Library key is needed at run time.
# `./core` in CORE_HOME is a wrapper with the release binary's command line.
# The engine's own requirements bring pandas and pyreadstat for the scripts.
FROM python:3.12-slim

ARG CORE_RELEASE=v1.0.0

RUN python3 -c "import urllib.request; urllib.request.urlretrieve('https://github.com/cdisc-org/cdisc-rules-engine/archive/refs/tags/${CORE_RELEASE}.tar.gz', '/tmp/core.tar.gz')" \
    && mkdir -p /opt/cdisc-core/core \
    && tar -xzf /tmp/core.tar.gz -C /opt/cdisc-core/core --strip-components=1 \
    && rm /tmp/core.tar.gz \
    && pip install --no-cache-dir --quiet /opt/cdisc-core/core PyYAML \
    && printf '#!/bin/sh\ncd /opt/cdisc-core/core && exec python3 core.py "$@"\n' > /opt/cdisc-core/core/core \
    && chmod +x /opt/cdisc-core/core/core \
    && cd /opt/cdisc-core/core && ./core version

ENV CORE_HOME=/opt/cdisc-core/core \
    CORE_LOCAL_RULES=/artifacts/rules \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /workspace
