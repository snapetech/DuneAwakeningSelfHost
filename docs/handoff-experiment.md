# Quick-Hiccup Handoff Experiment

Confidence low that true zero-disconnect live session migration exists in the
self-hosted stack. Confidence moderate that a very short outage may look
seamless if the client automatically reconnects to the same public endpoint and
the promoted host presents compatible world state quickly enough.

This experiment measures that behavior. It does not assume success.

## Hypothesis

The client may tolerate a brief interruption if:

- the public IP and ports stay the same;
- Postgres promotion is caught up and sealed;
- RabbitMQ TLS identity remains valid for the public address;
- the replacement stack reaches `current_alive_active=30 active_servers=30`
  quickly;
- the client reconnects internally before surfacing a manual disconnect.

## Runbook

Use a maintenance window or a disposable battlegroup first.

```sh
make handoff-ready ENV_FILE=.env ROLE=standby
make handoff-experiment ENV_FILE=.env ROLE=standby
CONFIRM_HANDOFF_EXPERIMENT=yes make handoff-experiment ENV_FILE=.env ROLE=standby APPLY=--apply
```

The dry-run captures baseline status under `captures/handoff/<timestamp>`. The
apply run performs the normal failover orchestration and captures before/after
status, RabbitMQ health, socket summaries, and an optional `tcpdump` pcap.

The harness refuses `--apply` when preflight fails unless
`DUNE_HANDOFF_ALLOW_PREFLIGHT_WARNINGS=yes` is set. Confidence high: a RabbitMQ
TLS SAN mismatch for the public address is a real client-reconnect risk and
should be fixed before testing seamless recovery.

If the RabbitMQ public SAN check fails, fix it in a maintenance window:

```sh
make rabbitmq-cert-stage ENV_FILE=.env
CONFIRM_INSTALL_STAGED_RMQ_CERT=yes make rabbitmq-cert-install-staged ENV_FILE=.env
CONFIRM_RECREATE_RMQ_TLS_STACK=yes make rabbitmq-cert-recreate-stack ENV_FILE=.env
make handoff-ready ENV_FILE=.env ROLE=standby
make handoff-experiment ENV_FILE=.env ROLE=standby
```

The recreate step restarts RabbitMQ TLS-dependent services so the broker and game
processes agree on the new certificate material.

Record the client result in `operator-notes.md`:

- no visible interruption;
- short freeze/rubber-band then resumes;
- reconnect spinner/loading screen then resumes;
- disconnect to menu but manual reconnect works;
- failed reconnect or stuck travel.

## Stop Conditions

Stop the experiment if both hosts can write the same `WORLD_UNIQUE_NAME`, if
Postgres seal/proof checks fail, or if router/NAT state cannot be clearly
restored.

## Expected Result

Confidence moderate: manual or automatic reconnect works after a short outage.
Confidence low: the same live in-memory session continues with no disconnect
semantics at all.

Summarize a capture after the run:

```sh
make summarize-handoff CAPTURE_DIR=captures/handoff/<timestamp>
```
