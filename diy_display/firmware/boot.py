import microcontroller, time

def timestamp():
    try:
        t = time.localtime()
        return "%04d-%02d-%02d %02d:%02d:%02d" % (
            t.tm_year, t.tm_mon, t.tm_mday,
            t.tm_hour, t.tm_min, t.tm_sec
        )
    except:
        return str(time.monotonic())

with open("/crashlog.txt", "a") as f:
    f.write("\n===== Boot =====\n")
    f.write("time=" + timestamp() + "\n")
    f.write("reset_reason=" + str(microcontroller.cpu.reset_reason) + "\n")
