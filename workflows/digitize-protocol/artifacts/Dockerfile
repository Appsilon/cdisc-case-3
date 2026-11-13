# digitize-protocol script image: Python + pypdf (PDF text layer) + jsonschema + the USDM 4.0 schema.
#
# Built by the platform from this carried file; scripts are not copied in, they
# run from /artifacts. The USDM 4.0 OpenAPI document (DDF-RA v4.0.0, 350 KB, over
# the carried-artifact cap) is fetched at a pinned commit and sha256-checked, so
# every run validates against the same bytes. stage-inputs copies it into the
# workspace for the agent's self-check, which runs in the catalog image.
FROM python:3.12-slim

ARG DDF_RA_COMMIT=aa303cb32f5d3ceecc68a16803e26720d2c1fc26
ARG USDM_API_SHA256=dc4303bca26256c56e5cb83222e898a09a5244472f7fd092b425cc2b7568fe19

RUN pip install --no-cache-dir --quiet pypdf==7.0.1 jsonschema==4.26.0 \
    && mkdir -p /opt/usdm \
    && python3 -c "import hashlib, sys, urllib.request; \
url = 'https://raw.githubusercontent.com/cdisc-org/DDF-RA/${DDF_RA_COMMIT}/Deliverables/API/USDM_API.json'; \
data = urllib.request.urlopen(url).read(); \
digest = hashlib.sha256(data).hexdigest(); \
sys.exit(f'USDM_API.json sha256 {digest} != ${USDM_API_SHA256}') if digest != '${USDM_API_SHA256}' else None; \
open('/opt/usdm/USDM_API.json', 'wb').write(data)"

ENV USDM_API_SOURCE=/opt/usdm/USDM_API.json \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /workspace
