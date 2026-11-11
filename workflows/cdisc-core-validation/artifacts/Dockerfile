# CDISC CORE validation image: Python + the pinned CORE rules engine release.
#
# Built by the platform from this carried file (context = the carried
# artifacts); scripts are not copied in, they run from /artifacts. CORE
# publishes x86_64 Linux builds only. The ubuntu-22.04 build is used because it
# needs glibc 2.35, which this Debian base provides. The release bundles its
# rules cache and CT packages, so no CDISC Library key is needed at run time.
FROM python:3.12-slim

ARG CORE_RELEASE=v1.0.0

RUN python3 -c "import urllib.request; urllib.request.urlretrieve('https://github.com/cdisc-org/cdisc-rules-engine/releases/download/${CORE_RELEASE}/core-ubuntu-22.04.tar.gz', '/tmp/core.tar.gz')" \
    && mkdir -p /opt/cdisc-core/release \
    && tar -xzf /tmp/core.tar.gz -C /opt/cdisc-core/release \
    && rm /tmp/core.tar.gz \
    && chmod +x /opt/cdisc-core/release/core/core \
    && ln -s /opt/cdisc-core/release/core /opt/cdisc-core/core \
    && cd /opt/cdisc-core/core && ./core version

RUN pip install --no-cache-dir pandas==2.2.3 pyreadstat==1.2.7 PyYAML==6.0.2

ENV CORE_HOME=/opt/cdisc-core/core \
    CORE_LOCAL_RULES=/artifacts/rules \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /workspace
