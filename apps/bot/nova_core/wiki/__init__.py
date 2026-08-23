# SPDX-License-Identifier: Apache-2.0
"""nova_core.wiki | wiki feature shim."""

from attu_wiki import WikiClient
from nova_core import __email__, __title__, __version__
from nova_core.client.core import config
from nova_core.wiki.documents import WikiViewDocument
from nova_core.wiki.repositories import WikiViewRepository, wire_wiki_command_repo


_wiki: WikiClient | None = None


def get_wiki() -> WikiClient:
    global _wiki  # noqa: PLW0603 - lazy singleton initialization requires global
    if _wiki is None:
        _wiki = WikiClient(endpoint=config.wiki.endpoint, user_agent=f'{__title__}/{__version__} ({__email__})')
    return _wiki


def init_repos(db) -> None:
    wire_wiki_command_repo(db.get_db())


def setup(bot):
    get_wiki()


from nova_core.manifest import FeatureManifest  # noqa: E402 - deferred to break circular import: manifest->tasks->nova_year->wiki


manifest = FeatureManifest(name='wiki', setup=setup, document_classes=[WikiViewDocument], repository_classes=[WikiViewRepository])
