import io
import re

f = "handlers/guest_handlers.py"
with io.open(f, "r", encoding="utf-8") as fh:
    c = fh.read()

# 1) Update imports: add GuestSessionService
old_import = "from services import CartService, MenuService, OrderService, TableService"
new_import = "from services import CartService, GuestSessionService, MenuService, OrderService, TableService"
if old_import in c:
    c = c.replace(old_import, new_import)
    print("IMPORT UPDATED")
else:
    print("IMPORT NOT FOUND")

# 2) Remove _invalidate_session and _require_active_table helper functions.
# Keep _send_dish and _invalidate_session is still referenced — we will
# replace _require_active_table with a thin wrapper around the service.
# Remove the big _require_active_table function (lines from its def to the
# blank line before create_guest_router).
pattern = re.compile(
    r'async def _require_active_table\([\s\S]*?\n    return table_number\n\n\n',
    re.MULTILINE,
)
new_c, n = pattern.subn('', c)
if n:
    c = new_c
    print("REMOVED _require_active_table", n)
else:
    print("_require_active_table NOT REMOVED")

# 3) Replace all calls "_require_active_table(" with a new helper that uses
# the service. We add a small adapter helper after _invalidate_session.
# Find all call sites and replace them.
#
# The old call pattern:
#   table_number = await _require_active_table(
#       state, table_service, <respond>, ...
#   )
# New pattern uses guest_session_service injected via kwargs:
#   table_number = await _require_active_table_session(
#       state, kwargs, <respond>, ...
#   )
# Simpler: define a new local async helper inside create_guest_router scope is
# not possible because calls are module-level functions. Instead, we keep a
# module-level _require_active_table that now delegates to the service.

# Insert the new _require_active_table helper right after _invalidate_session.
adapter = '''async def _require_active_table(
    state: FSMContext,
    guest_session_service: "GuestSessionService",
    respond,
    *,
    for_payment: bool = False,
) -> Optional[int]:
    """Validate the guest's table session via GuestSessionService.

    Thin adapter that reads FSM state, delegates the business logic to
    :class:`GuestSessionService`, and applies the resulting action (persisting
    the session token, invalidating on rescan, or surfacing an error message)
    back onto the aiogram layer.
    """
    data = await state.get_data()
    table_number = data.get("table_number")
    token = data.get("session_assigned_at")

    result = await guest_session_service.validate_table_session(
        table_number, token, for_payment=for_payment
    )

    if result.error_message is not None:
        await respond(result.error_message)

    if result.requires_rescan:
        await state.update_data(table_number=None, session_assigned_at=None)
        return None

    if result.session_assigned_at is not None:
        await state.update_data(session_assigned_at=result.session_assigned_at)

    return result.table_number


'''

# Insert the adapter right before create_guest_router definition.
marker = "def create_guest_router() -> Router:"
if marker in c and "async def _require_active_table(" not in c:
    c = c.replace(marker, adapter + marker)
    print("ADAPTER INSERTED")
else:
    print("ADAPTER NOT INSERTED (already present or marker missing)")

# 4) Rewrite call sites. Old signature uses (state, table_service, respond, ...).
# New signature uses (state, guest_session_service, respond, ...).
c = c.replace(
    "await _require_active_table(\n            state, table_service, message.answer\n        )",
    "await _require_active_table(\n            state, kwargs[\"guest_session_service\"], message.answer\n        )",
)
c = c.replace(
    "await _require_active_table(\n            state, table_service, message.answer, for_payment=True\n        )",
    "await _require_active_table(\n            state, kwargs[\"guest_session_service\"], message.answer, for_payment=True\n        )",
)
c = c.replace(
    'await _require_active_table(\n            state, table_service, lambda t: callback.answer(t, show_alert=True)\n        )',
    'await _require_active_table(\n            state, kwargs["guest_session_service"], lambda t: callback.answer(t, show_alert=True)\n        )',
)
c = c.replace(
    'await _require_active_table(\n            state,\n            table_service,\n            lambda t: callback.answer(t, show_alert=True),\n            for_payment=True,\n        )',
    'await _require_active_table(\n            state,\n            kwargs["guest_session_service"],\n            lambda t: callback.answer(t, show_alert=True),\n            for_payment=True,\n        )',
)

# 5) Remove now-unused table_service parameters from handlers that only used
# it for _require_active_table. We keep them for simplicity to avoid breaking
# the middleware DI signature; table_service is still used elsewhere too.

with io.open(f, "w", encoding="utf-8") as fh:
    fh.write(c)
print("DONE")
