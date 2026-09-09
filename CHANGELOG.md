# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-09-09

### Added

- Support for Python 3.9 to 3.14.
- The `Askpilot` and `AsyncAskpilot` clients, with an API key, a base URL, a timeout, retries,
  and an optional httpx client of your own.
- `client.organization.get()`.
- `client.workflows.list()`, `iterate()`, `get()`, and `start()`.
- A typed model for every object the API returns.
- One exception class for each kind of failure, all under `AskpilotError`, with the request id and
  the error code of the API.
- Retries after a connection error, a timeout, a 502, a 503, or a 504 on a `GET`, and after a
  429 on any request.
- One `DEBUG` log line per request and one `WARNING` before each retry, on the logger `askpilot`.

[Unreleased]: https://github.com/Askpilot-AI-Number/public-api-python-client-sdk/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Askpilot-AI-Number/public-api-python-client-sdk/releases/tag/v0.1.0
