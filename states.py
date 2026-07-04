"""FSM states for staff bot conversations."""
from aiogram.fsm.state import State, StatesGroup


class StaffStates(StatesGroup):
    """States for staff bot interactions."""
    
    # Authentication
    waiting_for_login = State()
    waiting_for_new_password = State()
    
    # Waiter management (admin)
    waiting_for_waiter_credentials = State()
    selecting_waiter = State()
    confirming_waiter_delete = State()

    # Table management
    waiting_for_waiter_name = State()
    unassigning_table = State()
    
    # Order management
    selecting_table = State()
    managing_orders = State()
    
    # Menu navigation (waiter)
    selecting_category = State()
    selecting_dish = State()
    selecting_quantity = State()