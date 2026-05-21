# Passworded Handoff Lab

Confidence high: the lab can test Dune process, Postgres dump/restore, RabbitMQ,
partition health, and host-to-host handoff mechanics without changing the live
router forwards or live production ports.

Confidence low: the lab can prove client-visible seamless reconnect unless the
Funcom/FLS token is authorized for the lab `WORLD_UNIQUE_NAME`. With the live
token copied into a different lab battlegroup name, Director returns
`ACCESS_DENIED`.

## Shape

The lab is a separate Compose project:

```sh
COMPOSE_PROJECT_NAME=dune_handoff_lab
```

It uses `compose.handoff-lab.yaml`, separate bind-mounted data under
`data/handoff-lab/`, a separate Docker network, and alternate host ports:

```sh
GAME_RMQ_PUBLIC_PORT=32982
GAME_UDP_PORT_RANGE=17777:17777
IGW_UDP_PORT_RANGE=18888:18888
POSTGRES_BRIDGE_PUBLIC_PORT=16432
```

The lab world is passworded through:

```sh
DUNE_SERVER_LOGIN_PASSWORD=change-me-lab-password
```

Do not forward the lab ports from the router unless deliberately running an
external client experiment. The default `EXTERNAL_ADDRESS=127.0.0.1` keeps the
lab non-public.

## Setup

Create a local lab env from the template:

```sh
cp .env.handoff-lab.example .env.handoff-lab
```

Set the lab secrets and `DUNE_SERVER_LOGIN_PASSWORD`. If testing real client
login, also set a Funcom/FLS token authorized for the lab
`WORLD_UNIQUE_NAME`; reusing a token for another battlegroup is expected to fail
with `ACCESS_DENIED`.

Validate without starting containers:

```sh
make handoff-lab-config ENV_FILE=.env.handoff-lab
```

## Local Lab

Start or repair the local lab:

```sh
make handoff-lab-up ENV_FILE=.env.handoff-lab
```

Check health:

```sh
make handoff-lab-status ENV_FILE=.env.handoff-lab
```

A healthy process-level lab has one current partition, one active server, and
game/admin RabbitMQ service-user connections. The stronger client-visible proof
also needs successful Director/Gateway FLS calls and an external test client.

Stop the lab:

```sh
make handoff-lab-stop ENV_FILE=.env.handoff-lab
```

## Remote Lab

Sync the lab files and env to the other host before using remote targets:

```sh
rsync -a .env.handoff-lab .env.handoff-lab.example compose.handoff-lab.yaml scripts/handoff-lab.sh kspls0:/home/keith/Documents/code/DuneAwakeningSelfHost/
```

Start, check, or stop the remote lab:

```sh
make handoff-lab-remote-up ENV_FILE=.env.handoff-lab REMOTE=kspls0
make handoff-lab-remote-status ENV_FILE=.env.handoff-lab REMOTE=kspls0
make handoff-lab-remote-stop ENV_FILE=.env.handoff-lab REMOTE=kspls0
```

## Bidirectional Handoff Drill

Move the lab from local to remote:

```sh
make handoff-lab ENV_FILE=.env.handoff-lab SRC=local DST=kspls0
```

Move it back:

```sh
make handoff-lab ENV_FILE=.env.handoff-lab SRC=kspls0 DST=local
```

The scripted handoff dumps the source lab database, stops source lab writers,
restores the dump on the destination, starts the destination lab stack, and
prints destination health. It does not touch production Compose projects,
production `data/postgres`, production router forwards, public `/32` ownership,
or live static-site service ownership.

## Client Experiment Gate

Before testing seamless reconnect with a real client, all of these must be true:

- the lab `WORLD_UNIQUE_NAME` is authorized by the configured FLS token;
- the lab RabbitMQ TLS certificate SAN covers the public host used by the test;
- the router forwards only lab ports to the lab host, never production ports;
- the lab world has a non-empty `DUNE_SERVER_LOGIN_PASSWORD`;
- only one side of the lab is writing at a time.

If any step requires both lab hosts to write the same world state concurrently,
stop the experiment. That is split-brain, not handoff.
