from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from app.services import users as users_service

class RoleFilter(BaseFilter):
    def __init__(self, roles: set[str]):
        self.roles = roles

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        tg_id = event.from_user.id
        users_service.get_or_create_user(tg_id, event.from_user.username) 
        role = users_service.get_role(tg_id)
        return role in self.roles
