### Build ESPHome Update
ARG BUILD_FROM
FROM $BUILD_FROM

# Packages
RUN \
  apk add --no-cache \
    python3-dev=~3.12 \
    py3-pip=~24.3 \
    libmagic=~5.46

RUN \
  apk add --no-cache --virtual .build-dependencies \
    build-base=~0.5 \
    git=~2.47.2 \
    docker=~27.3.1 \
    nginx

# Prepare
RUN \
  cp /usr/bin/docker /usr/local/bin/.undocked

# Python
COPY requirements.txt /

RUN pip install  --break-system-packages -r requirements.txt && \
    rm requirements.txt

# Port
EXPOSE 5500

# Build arguments
ARG BUILD_ARCH
ARG BUILD_DATE
ARG BUILD_DESCRIPTION
ARG BUILD_NAME
ARG BUILD_REF
ARG BUILD_REPOSITORY
ARG BUILD_VERSION

# Add Label
LABEL \
    io.hass.name="${BUILD_NAME}" \
    io.hass.description="${BUILD_DESCRIPTION}" \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="addon" \
    io.hass.version=${BUILD_VERSION} \
    maintainer="Andrew J.Swan <andrewjswan@addons.community>" \
    org.opencontainers.image.title="${BUILD_NAME}" \
    org.opencontainers.image.description="${BUILD_DESCRIPTION}" \
    org.opencontainers.image.vendor="Andrew J.Swan" \
    org.opencontainers.image.authors="Andrew J.Swan <andrewjswan@addons.community>" \
    org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.created=${BUILD_DATE} \
    org.opencontainers.image.revision=${BUILD_REF} \
    org.opencontainers.image.version=${BUILD_VERSION}

WORKDIR /

# Copy root filesystem
COPY rootfs /

# Make scripts executable
RUN chmod a+x $(find "./" -type f -iname "*.sh")
RUN chmod a+x $(find "./etc/s6-overlay/s6-rc.d" -type f -iname "*")
RUN chmod a+x $(find "./etc/services.d" -type f -iname "*")

WORKDIR /app

# Copy data for add-on
COPY app .

# Start ESPHome Update
RUN echo ${BUILD_ARCH} > /arch
CMD [ "./run.sh" ]
