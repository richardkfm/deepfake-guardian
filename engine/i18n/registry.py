"""Language pack registry with auto-discovery.

On first use the registry imports every module in ``engine/i18n/packs/`` and
collects all :class:`~i18n.base.LanguagePack` subclasses by their
``lang_code``.  Adding a new language = creating one new file in that
directory.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from i18n.base import LanguagePack

logger = logging.getLogger(__name__)


class LanguageRegistry:
    """Singleton registry that maps language codes to :class:`LanguagePack` instances."""

    _packs: dict[str, "LanguagePack"] = {}
    _discovered: bool = False

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    @classmethod
    def discover(cls) -> None:
        """Import all modules in ``i18n/packs/`` and register their packs."""
        from i18n import packs as packs_pkg
        from i18n.base import LanguagePack

        for _, module_name, _ in pkgutil.iter_modules(packs_pkg.__path__):
            try:
                importlib.import_module(f"i18n.packs.{module_name}")
            except Exception:
                logger.warning("Failed to import language pack module: %s", module_name)

        # Recursively collect all LanguagePack subclasses
        def _collect(cls_: type) -> list[type]:
            result: list[type] = []
            subclasses: list[type] = cls_.__subclasses__()
            for sub in subclasses:
                result.append(sub)
                result.extend(_collect(sub))
            return result

        for pack_cls in _collect(LanguagePack):
            code = getattr(pack_cls, "lang_code", None)
            if code and code not in cls._packs:
                try:
                    cls._packs[code] = pack_cls()
                    logger.info("Language pack registered: %s (%s)", code, pack_cls.__name__)
                except Exception:
                    logger.warning("Failed to instantiate language pack: %s", pack_cls.__name__)

        cls._discovered = True

    @classmethod
    def _ensure_discovered(cls) -> None:
        if not cls._discovered:
            cls.discover()

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    @classmethod
    def get(cls, lang_code: str) -> "LanguagePack | None":
        """Return the pack for *lang_code*, or ``None`` if not registered."""
        cls._ensure_discovered()
        return cls._packs.get(lang_code)

    @classmethod
    def get_enabled(cls, enabled_codes: list[str]) -> list["LanguagePack"]:
        """Return packs whose codes appear in *enabled_codes*."""
        cls._ensure_discovered()
        return [cls._packs[code] for code in enabled_codes if code in cls._packs]

    @classmethod
    def all_packs(cls) -> dict[str, "LanguagePack"]:
        """Return a copy of the full registry dict."""
        cls._ensure_discovered()
        return dict(cls._packs)

    @classmethod
    def reset(cls) -> None:
        """Clear registry (used in tests to force re-discovery)."""
        cls._packs = {}
        cls._discovered = False
