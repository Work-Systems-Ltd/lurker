FROM andrius/asterisk:22

COPY conf/ /etc/asterisk/

EXPOSE 5060/udp
EXPOSE 10000-10100/udp

CMD ["asterisk", "-fvvv"]
