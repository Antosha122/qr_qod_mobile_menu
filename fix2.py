import io

f = "handlers/staff_handlers.py"
with io.open(f, "r", encoding="utf-8") as fh:
    c = fh.read()

old_line = '        table_info = await _build_table_info(current_user_id, is_admin=is_admin, **kwargs)'
new_lines = '        # Business logic moved to TableService.get_table_overview()\n        table_service: TableService = kwargs["table_service"]\n        table_info = await table_service.get_table_overview(current_user_id, is_admin=is_admin)'

# 1) Replace the call site inside show_tables
if old_line in c:
    c = c.replace(old_line, new_lines)
    print("CALL SITE REPLACED")
else:
    print("CALL SITE NOT FOUND")

# 2) Remove the _build_table_info function definition
import re
pattern = r'    async def _build_table_info\(current_user_id, is_admin=False, \*\*kwargs\):\n        table_service: TableService = kwargs\["table_service"\]\n        cart_service: CartService = kwargs\["cart_service"\]\n        info = \{\}\n        for assignment in await table_service\.get_all_open_tables\(\):\n            total = await cart_service\.get_cart_total\(assignment\.table_number\)\n            info\[assignment\.table_number\] = \{"is_open": True, "is_mine": is_admin or assignment\.waiter_id == current_user_id, "total": total, "payment_status": assignment\.payment_status\}\n        return info\n\n'
new_c, n = re.subn(pattern, '', c)
if n:
    c = new_c
    print("FUNC REMOVED", n)
else:
    print("FUNC NOT REMOVED")

with io.open(f, "w", encoding="utf-8") as fh:
    fh.write(c)
print("DONE")
