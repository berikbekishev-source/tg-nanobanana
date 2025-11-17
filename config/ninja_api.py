from __future__ import annotations

import inspect
from typing import Any

from ninja import NinjaAPI


def build_ninja_api(*, disable_csrf: bool = True, **kwargs: Any) -> NinjaAPI:
    """
    Создаёт NinjaAPI и аккуратно отключает CSRF даже для старых версий пакета.

    В последних версиях django-ninja параметр ``csrf`` из конструктора пропал,
    поэтому держим совместимость через reflection.
    """
    params = inspect.signature(NinjaAPI.__init__).parameters
    if disable_csrf and "csrf" in params:
        return NinjaAPI(csrf=False, **kwargs)

    api_instance = NinjaAPI(**kwargs)
    if disable_csrf:
        setattr(api_instance, "csrf", False)
    return api_instance
