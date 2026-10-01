# Reporting a security issue

Do not attach credentials, personal recordings or a complete user profile to public issues. When GitHub private vulnerability reporting is enabled for this repository, use the **Security → Report a vulnerability** form. If it is unavailable, contact the maintainer through a private channel before sharing exploit details.

Flow's MCP connection is local stdio, with typed tools and a read-only mode. There is no built-in remote MCP listener. A trusted MCP client still has access to the data and actions exposed by its connection; read-only access can read history, but cannot change settings, record audio, transcribe files or download components. Python extensions are opt-in and run with the user's account permissions.

API audio uploads require the user's saved consent. Credentials use account-bound DPAPI on Windows and user-only files on Linux. MCP reads exclude credentials. The loopback Linux settings server validates its session path, host, origin and method allowlist and rejects framing. Releases include checksums. Windows downloads are currently unsigned and can show SmartScreen; optional signed releases require trusted timestamped signatures.

For routine speech problems, the in-app diagnostic report uses bundled test audio and excludes personal recordings, history and API keys. Review any attachment before sending it.
