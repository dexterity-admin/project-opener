"""Zoho Cliq bot client (brief section 3.5).  Owner: builder 1 (CORE+HUB).

One office bot under a shared service account; one token in Settings, stored
with DPAPI (``Settings.cliq_token``).  The client:

* ``lookup_user(email)`` -> Cliq user id (linked once per user in Settings);
* ``dm(user_ids, text)``: the bot messages those users; the text carries a
  ``projectopener://`` link;
* ``post_channel(channel, text)`` for watchers that post to a channel;
* an outbox (``data_dir()/cliq-outbox.jsonl``) retried every ``CLIQ_RETRY_S``
  when Cliq is unreachable; the toast never waits for Cliq.

Open (verify against Zoho's API documentation before building): which
endpoint and token type fit "one token that does not expire" (the bot's
incoming-webhook ``zapikey`` vs an OAuth refresh token), whether that endpoint
can target users by id or e-mail, and the data centre (cliq.zoho.in vs .com).
Standard library only (``urllib.request``), timeouts of 10 s, no retries inline.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class CliqResult:
    ok: bool
    status: int = 0
    message: str = ""


class CliqClient:
    def __init__(self, api_base: str, bot: str, token: str, outbox: Path):
        self.api_base = api_base.rstrip("/")
        self.bot = bot
        self.token = token
        self.outbox = Path(outbox)

    @property
    def configured(self) -> bool:
        return bool(self.api_base and self.bot and self.token)

    def lookup_user(self, email: str) -> str:
        raise NotImplementedError("CliqClient.lookup_user")

    def dm(self, user_ids: list[str], text: str) -> CliqResult:
        raise NotImplementedError("CliqClient.dm")

    def post_channel(self, channel: str, text: str) -> CliqResult:
        raise NotImplementedError("CliqClient.post_channel")

    def queue(self, kind: str, target: list[str] | str, text: str) -> None:
        raise NotImplementedError("CliqClient.queue")

    def flush_outbox(self) -> int:
        """Retry queued messages; returns how many went out."""
        raise NotImplementedError("CliqClient.flush_outbox")
