# Security

Do not post self-hosting/FLS tokens, local passwords, RabbitMQ cookies, TLS private keys, server logs, database dumps, or generated saved data in issues or pull requests.

If you accidentally commit a secret:

1. Revoke or rotate it immediately.
2. Remove it from the repository history before pushing, or force-push a cleaned branch if it was already pushed.
3. Treat runtime logs as sensitive because they may contain hostnames, IPs, tokens, player identifiers, or service registration details.

This repository does not accept reports about bypassing game authentication, cheating, exploit automation, or unauthorized redistribution of Funcom software.
