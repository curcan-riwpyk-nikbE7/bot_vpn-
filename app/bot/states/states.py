"""FSM states for multi-step flows."""

from aiogram.fsm.state import State, StatesGroup


class AddServer(StatesGroup):
    name = State()
    url = State()
    login = State()
    password = State()


class AddTariff(StatesGroup):
    name = State()
    days = State()
    price = State()
    devices = State()


class EditTariff(StatesGroup):
    choosing = State()
    field = State()
    value = State()


class Mailing(StatesGroup):
    target = State()
    text = State()
    confirm = State()


class EditSetting(StatesGroup):
    key = State()
    value = State()


class SearchClient(StatesGroup):
    query = State()


class Customize(StatesGroup):
    name = State()
    greeting = State()
    logo = State()
    support = State()
    phone = State()
    trial_days = State()
    channel_url = State()
