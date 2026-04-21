FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    baresip \
    baresip-core \
    espeak-ng \
    sox \
    && rm -rf /var/lib/apt/lists/*

# Generate test audio files (8kHz 16-bit mono WAV, what baresip/ulaw needs)
RUN espeak-ng "Hello, this is Alice calling about the quarterly report. I wanted to discuss the budget numbers and timeline for the project." \
    --stdout | sox - -r 8000 -c 1 -b 16 /alice.wav && \
    espeak-ng "Hi Alice, thanks for calling. The budget looks good but we need to push the deadline back two weeks. Let me send you the updated schedule." \
    --stdout | sox - -r 8000 -c 1 -b 16 /bob.wav

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
