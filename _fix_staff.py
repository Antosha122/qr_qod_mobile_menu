import io

f = 'handlers/staff_handlers.py'
with io.open(f, 'r', encoding='utf-8') as fh:
    c = fh.read()

old_block = '''    async def _build_table_info(current_user_id, is_admin=False, **kwargs):
        table_service: TableService = kwargs["table_service"]
        cart_service: CartService = kwargs["cart_service"]
        info = {}
        for assignment in await table_service.get_all_open_tables():
            total = await cart_service.get_cart_total(assignment.table_number)
            info[assignment.table_number] = {"is_open": True, "is_mine": is_admin or assignment.waiter_id == current_user_id, "total": total, "payment_status": assignment.payment_status}
        return info

    @router.message(F.text == "\U0001F374 Столы")
    async def show_tables(message: Message, state: FSMContext, **kwargs):
        session = await get_session(message.from_user.id)
        if not session:
            await message.answer("\u274C Сначала войдите в систему.")
            return
        user = await kwargs["auth_service"].get_user_by_username(session)
        current_user_id = user.id if user else None
        is_admin = bool(user and user.role == "admin")
        table_info = await _build_table_info(current_user_id, is_admin=is_admin, **kwargs)
        await message.answer("\U0001F374 Выберите стол:", reply_markup=get_table_selection_keyboard(table_info))
        await state.set_state(StaffStates.selecting_table)'''

new_block = '''    @router.message(F.text == "\U0001F374 Столы")
    async def show_tables(message: Message, state: FSMContext, **kwargs):
        table_service: TableService = kwargs["table_service"]
        session = await get_session(message.from_user.id)
        if not session:
            await message.answer("\u274C Сначала войдите в систему.")
            return
        user = await kwargs["auth_service"].get_user_by_username(session)
        current_user_id = user.id if user else None
        is_admin = bool(user and user.role == "admin")
        table_info = await table_service.get_table_overview(current_user_id, is_admin=is_admin)
        await message.answer("\U0001F374 Выберите стол:", reply_markup=get_table_selection_keyboard(table_info))
        await state.set_state(StaffStates.selecting_table)'''

if old_block in c:
    c = c.replace(old_block, new_block)
    with io.open(f, 'w', encoding='utf-8') as fh:
        fh.write(c)
    print('REPLACED OK')
else:
    print('OLD BLOCK NOT FOUND')
