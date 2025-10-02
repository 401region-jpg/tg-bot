# states.py
from aiogram.fsm.state import StatesGroup, State

class ProfileStates(StatesGroup):
    name = State()
    age = State()
    bio = State()
    photo = State()

# можно добавить states для редактирования отдельных полей
class EditStates(StatesGroup):
    edit_name = State()
    edit_age = State()
    edit_bio = State()
    edit_photo = State()
