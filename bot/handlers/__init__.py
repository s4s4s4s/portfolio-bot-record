from aiogram import Router

from bot.handlers import admin, booking, cancel_booking, my, nlu, reschedule, start


def build_root_router() -> Router:
    """Собирает все роутеры в один корневой. Порядок имеет значение:
    admin-роутер первым, чтобы IsAdmin-фильтры перехватывали раньше.
    NLU-последний — ловит всё что не перехватили команды / callback.
    """
    root = Router(name="root")
    root.include_router(start.router)
    root.include_router(admin.router)
    root.include_router(booking.router)
    root.include_router(cancel_booking.router)
    root.include_router(reschedule.router)
    root.include_router(my.router)
    root.include_router(nlu.router)
    return root


__all__ = ["build_root_router"]
