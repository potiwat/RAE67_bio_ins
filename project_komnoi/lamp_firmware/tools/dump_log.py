"""อ่าน lamp.log บนบอร์ด (เพราะ REPL ถูกปลดจาก UART0 ตอนรัน main.py)
    import tools.dump_log
"""
try:
    with open("lamp.log") as f:
        print(f.read())
except OSError:
    print("ยังไม่มี lamp.log")
