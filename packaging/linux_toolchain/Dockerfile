ARG UBUNTU_IMAGE
FROM --platform=linux/amd64 ${UBUNTU_IMAGE}
ARG UBUNTU_SNAPSHOT
ENV DEBIAN_FRONTEND=noninteractive
# Bootstrap HTTPS trust from Noble's original, signed release pocket only.
# The minimal base has no CA bundle; the snapshot service redirects to HTTPS.
RUN rm -f /etc/apt/sources.list.d/ubuntu.sources && \
    printf 'deb http://archive.ubuntu.com/ubuntu noble main\n' > /etc/apt/sources.list && \
    apt-get update --error-on=any && \
    apt-get install -y --no-install-recommends ca-certificates=20240203
# All subsequent upgrades and build tools come from the frozen snapshot.
RUN test -n "$UBUNTU_SNAPSHOT" && \
    printf 'deb [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/%s noble main universe\ndeb [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/%s noble-updates main universe\ndeb [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/%s noble-security main universe\n' \
      "$UBUNTU_SNAPSHOT" "$UBUNTU_SNAPSHOT" "$UBUNTU_SNAPSHOT" > /etc/apt/sources.list && \
    apt-get update --error-on=any && apt-get dist-upgrade -y && \
    apt-get install -y --no-install-recommends \
      verilator make g++ perl python3 bash dash coreutils findutils
# Preparing the real compiler wrapper imports board/i18n (QtCore). This is a
# builder-only dependency and is not part of the exported SDK package closure.
RUN apt-get install -y --no-install-recommends python3-pyqt6
WORKDIR /src
COPY fpga_lab /src/fpga_lab
COPY packaging/linux_toolchain /src/packaging/linux_toolchain
ENTRYPOINT ["python3", "/src/packaging/linux_toolchain/container_build.py"]
