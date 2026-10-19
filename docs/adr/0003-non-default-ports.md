# 3. Publish every service on a non-default host port

Date: 2026-10-19
Status: Accepted

## Context
Other projects on the same machine already occupy the conventional
ports: Postgres 5432, a frontend on 3000, FastAPI on 8000. Binding
LogWatch to the defaults caused "port is already allocated" failures
on `docker compose up`.

## Decision
Publish each service one above its default on the host, bound to
127.0.0.1:

| Service  | Host  | Container |
|----------|-------|-----------|
| Postgres | 5433  | 5432      |
| Grafana  | 3001  | 3000      |
| API      | 8001  | 8000      |

Container-internal ports stay at their defaults, so service-to-service
traffic on the Compose network is unaffected.

## Consequences
+ LogWatch runs alongside other projects without conflicts.
+ Binding to 127.0.0.1 keeps services off the local network.
- Documentation and curl examples must use the non-default ports;
  the README carries this table.
